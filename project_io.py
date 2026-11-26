"""Scoped review exports and bounded, read-only XLSX import preview.

The preview never writes a ledger. The regular revision-checked save commits
project, people and claims together after the user reviews them.
"""
import base64
import binascii
import csv
import io
import math
import posixpath
import re
from datetime import date, timedelta, datetime, timezone
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET
from xml.dom import minidom
from xml.parsers.expat import ExpatError
from engine import analyze, convert, QUALIFICATION_LEVELS, VERSION

FIELDS = [
    ('姓名', 'name'), ('所属单位', 'company'), ('工号', 'code'),
    ('职称', 'title'), ('职称有效开始', 'title_from'), ('职称有效结束', 'title_to'),
    ('职称证明依据', 'title_source'), ('投入开始', 'start'), ('投入结束', 'end'),
    ('申报数量', 'amount'), ('申报单位', 'unit'), ('申报日期', 'submitted_at'),
    ('申报计费等级', 'grade'), ('申报单价', 'price'), ('单价单位', 'price_unit'),
    ('合同对应职称', 'basis_title'), ('依据允许等级', 'allowed_grade'),
    ('依据单价', 'basis_price'), ('依据单价单位', 'basis_unit'),
    ('计价有效开始', 'basis_from'), ('计价有效结束', 'basis_to'), ('合同或计价依据', 'basis_source'),
]
PERSON_KEYS = {key for _, key in FIELDS[:7]}
COMPACT_FIELDS=[('人员选择','person_choice'),('申报数量','amount'),('申报单位（可选）','unit'),
                ('投入开始（可选）','start'),('投入结束（可选）','end'),
                ('新人员姓名','name'),('新人员单位','company'),('新人员工号','code')]
COMPACT_HINT_HEADERS = [label for label, _ in COMPACT_FIELDS[:5]] + [
    '姓名（仅新人）', '单位（仅新人）', '工号（仅新人）', '本行填写提示',
]
GRID_FIELDS = [
    ('选择人员', 'person_choice'), ('姓名', 'name'), ('工号', 'code'), ('单位', 'company'),
    ('职称', 'title'), ('有效期', 'validity'), ('职称证明（选填）', 'title_source'),
    ('申报数量', 'amount'), ('申报单位', 'unit'), ('投入开始', 'start'), ('投入结束', 'end'),
]
GRID_HEADERS = [label for label, _ in GRID_FIELDS]
GRID_REFERENCE_HEADERS = ['已有人员选择', *GRID_HEADERS[1:6], '职称证明（可选）', *GRID_HEADERS[7:]]
DATED_VALIDITY = '固定时间段内有效'
LONG_VALIDITY = '长期有效'
DATE_NOT_REQUIRED = '无需填写'
DATED_GRID_FIELDS = GRID_FIELDS[:9] + [
    ('投入开始（如 2025/4/4）', 'start'), ('投入结束（如 2025/4/30）', 'end'),
    ('证书有效开始（如 2025/4/4）', 'title_from'), ('证书有效结束（如 2026/4/4）', 'title_to'),
]
DATED_GRID_HEADERS = [label for label, _ in DATED_GRID_FIELDS]
NEW_PERSON = '新增人员'
DATE_KEYS = {'title_from','title_to','start','end','submitted_at','basis_from','basis_to'}
NUMBER_KEYS = {'amount','price','basis_price'}
NS = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
SHEET_NS = NS['s']
REL_ID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'

def person_choice(person):
    return f"{person['name']} · {person.get('company','')} · {person['code']}"

def workbook_xml(package, name):
    content = package.read(name)
    if b'\0' in content or b'<!DOCTYPE' in content or b'<!ENTITY' in content:
        raise ValueError('Excel XML 格式不受支持')
    return content

def worksheet_path(workbook, relationships, name):
    sheet = next((s for s in workbook.findall('s:sheets/s:sheet', NS) if s.get('name') == name), None)
    if sheet is None:
        raise ValueError(f'未找到“{name}”工作表，请使用系统下载的模板')
    rel = next((r for r in relationships if r.get('Id') == sheet.get(REL_ID)
                and r.get('TargetMode') != 'External' and (r.get('Type') or '').endswith('/worksheet')), None)
    target = rel.get('Target', '') if rel is not None else ''
    path = posixpath.normpath(target[1:] if target.startswith('/') else posixpath.join('xl', target))
    if not path.startswith('xl/worksheets/') or not path.endswith('.xml'):
        raise ValueError('Excel 工作表路径无效')
    return path

def decode_xlsx(encoded):
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Excel 文件编码无效')
    if len(raw) > 8_000_000:
        raise ValueError('Excel 文件不得超过8MB')
    return raw

def check_xlsx_package(package):
    files = package.infolist()
    if len(files) > 500 or sum(item.file_size for item in files) > 30_000_000:
        raise ValueError('Excel 解压后过大')

def refresh_template(encoded, state):
    try:
        return selection_template(decode_xlsx(encoded), state, refresh=True)
    except (BadZipFile, KeyError, ET.ParseError, ExpatError):
        raise ValueError('无法更新人员下拉，请选择系统下载的有效 .xlsx 模板')

def selection_template(template, state, *, refresh=False):
    """Update the dropdown source without changing the entered claims."""
    out = io.BytesIO()
    ns = '{' + SHEET_NS + '}'
    with ZipFile(io.BytesIO(template)) as source, ZipFile(out,'w',ZIP_DEFLATED) as target:
        check_xlsx_package(source)
        wb = ET.fromstring(workbook_xml(source, 'xl/workbook.xml'))
        rels = ET.fromstring(workbook_xml(source, 'xl/_rels/workbook.xml.rels'))
        roster = worksheet_path(wb, rels, '人员选项')
        main = worksheet_path(wb, rels, '人员工时')
        if roster == main:
            raise ValueError('人员工时与人员选项必须是不同工作表')
        main_xml = workbook_xml(source, main)
        headers = list(workbook_headers(source, main_xml))
        dated_grid = not refresh or DATED_GRID_HEADERS in headers
        grid = dated_grid or any(header in (GRID_HEADERS, GRID_REFERENCE_HEADERS) for header in headers)
        epoch = wb.find('s:workbookPr', NS)
        epoch = epoch is not None and epoch.get('date1904') in ('1', 'true')
        roster_rows = roster_values(state, grid, dated=dated_grid)
        formula_text = f'INDIRECT("\'人员选项\'!$A$2:$A${max(2, len(roster_rows))}")'
        for item in source.infolist():
            content=source.read(item.filename)
            if item.filename == roster:
                content = update_roster_xml(workbook_xml(source, roster), roster_rows, epoch=epoch)
            elif item.filename == main:
                content = update_dropdown_xml(main_xml, formula_text)
                if not refresh: content = grid_template_sheet(content)
                elif dated_grid: content = refresh_certificate_formulas(content)
            elif item.filename == 'xl/workbook.xml':
                calculation = wb.find('s:calcPr', NS)
                if calculation is None:
                    calculation = ET.SubElement(wb, ns+'calcPr')
                calculation.attrib.update(calcMode='auto', fullCalcOnLoad='1', forceFullCalc='1', calcOnSave='1')
                content = ET.tostring(wb, encoding='utf-8', xml_declaration=True)
            elif not refresh and item.filename == 'xl/styles.xml':
                root = ET.fromstring(content)
                styles = ET.SubElement(root, ns+'dxfs', count='1')
                style = ET.SubElement(styles, ns+'dxf')
                fill = ET.SubElement(ET.SubElement(style, ns+'fill'), ns+'patternFill', patternType='solid')
                ET.SubElement(fill, ns+'fgColor', rgb='FFE8EDF2')
                ET.SubElement(fill, ns+'bgColor', rgb='FFE8EDF2')
                styles.set('count', '3')
                for color in ('FFFFE4AC', 'FFFFF4DE'):
                    style = ET.SubElement(styles, ns+'dxf')
                    fill = ET.SubElement(ET.SubElement(style, ns+'fill'), ns+'patternFill', patternType='solid')
                    ET.SubElement(fill, ns+'fgColor', rgb=color)
                    ET.SubElement(fill, ns+'bgColor', rgb=color)
                content = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            elif not refresh and item.filename == 'xl/worksheets/sheet3.xml':
                root = ET.fromstring(content)
                notes = {
                    'A1': '人员工时录入模板',
                    'A2': '已有人员',
                    'B2': '在 A 列下拉选人，B～G 自动显示人员资料，L、M 自动带出证书日期；长期有效时显示“无需填写”。只填 H～K 的本次申报。',
                    'A4': '日期及单位',
                    'B4': '按列标题的示例输入日期。申报单位可选工日、工时。姓名相同请按单位和工号核对。',
                    'A5': '新增人员',
                    'B5': '长期有效时 F 可留空，表尾 L、M 自动显示“无需填写”。仅有固定期限时，F 选“固定时间段内有效”，再填高亮的 L、M 两列。',
                    'A6': '导入后继续编辑',
                    'B6': '导入后可在网页表内修改。若已手填新人资料，改选已有人员时请使用空白行，保留自动带出资料的公式。',
                    'B7': '每次点击“下载模板”，人员下拉名单都会读取当前台账。',
                    'B8': '在网页核对人员、日期和数量，填写操作人后点击“保存并核验”。如公共信息有遗漏，可补充后重新解析文件。',
                }
                for cell in root.findall('s:sheetData/s:row/s:c', NS):
                    if cell.get('r') in notes:
                        cell.find('s:v', NS).text = notes[cell.get('r')]
                content = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            target.writestr(item,content)
    return out.getvalue()

def grid_template_sheet(content):
    root = ET.fromstring(content)
    ns = '{' + SHEET_NS + '}'
    columns = root.find('s:cols', NS)
    for column in list(columns):
        columns.remove(column)
    for i, width in enumerate((33, 13, 13, 20, 18, 24, 19, 12, 12, 25, 25, 29, 29), 1):
        ET.SubElement(columns, ns+'col', min=str(i), max=str(i), width=str(width), customWidth='1')

    header, *rows = root.findall('s:sheetData/s:row', NS)
    for cell in list(header):
        header.remove(cell)
    for i, label in enumerate(DATED_GRID_HEADERS):
        cell = ET.SubElement(header, ns+'c', r=f'{chr(65+i)}1', s='4', t='str')
        ET.SubElement(cell, ns+'v').text = label
    for row in rows:
        number = row.get('r')
        for cell in list(row):
            row.remove(cell)
        for index, style in enumerate(('5','2','6','2','2','6','2','8','2','10','10','10','10'), 1):
            cell = ET.SubElement(row, ns+'c', r=f'{chr(64+index)}{number}', s=style)
            if 2 <= index <= 7:
                cell.set('t', 'str')
                choice = f'$A{number}'
                # VLOOKUP treats wildcard characters as patterns, even in exact mode.
                lookup = f'SUBSTITUTE(SUBSTITUTE(SUBSTITUTE({choice},"~","~~"),"*","~*"),"?","~?")'
                ET.SubElement(cell, ns+'f').text = (
                    f'IF({choice}="","",IF({choice}="{NEW_PERSON}",'
                    '"",'
                    f'IFERROR(VLOOKUP({lookup},\'人员选项\'!$A:$G,{index},FALSE),"")))'
                )
                ET.SubElement(cell, ns+'v')
            elif index in (12, 13):
                ET.SubElement(cell, ns+'f').text = certificate_date_formula(number, index-4)
                ET.SubElement(cell, ns+'v')
    validations = root.find('s:dataValidations', NS)
    unit = validations.find('s:dataValidation[@sqref="C2:C2001"]', NS)
    unit.set('sqref', 'I2:I2001')
    unit.set('showErrorMessage', '1')
    unit.find('s:formula1', NS).text = '"工日,工时"'
    title = ET.SubElement(validations, ns+'dataValidation', type='list', sqref='E2:E2001', allowBlank='1')
    ET.SubElement(title, ns+'formula1').text = '"技术专家,项目经理,高级技术人员,一般技术人员"'
    validity = ET.SubElement(validations, ns+'dataValidation', type='list', sqref='F2:F2001',
                             allowBlank='1', showErrorMessage='1', showInputMessage='1',
                             prompt='已有人员自动带出。新增人员长期有效可留空；固定期限请填表尾 L、M 两列。')
    ET.SubElement(validity, ns+'formula1').text = f'"{LONG_VALIDITY},{DATED_VALIDITY}"'
    validations.set('count', str(len(validations)))
    formatting = ET.Element(ns+'conditionalFormatting', sqref='B2:G2001')
    rule = ET.SubElement(formatting, ns+'cfRule', type='expression', dxfId='0', priority='1')
    ET.SubElement(rule, ns+'formula').text = f'AND($A2<>"",$A2<>"{NEW_PERSON}")'
    root.insert(list(root).index(validations), formatting)
    fixed_term = f'AND($A2="{NEW_PERSON}",$F2="{DATED_VALIDITY}")'
    dates_format = ET.Element(ns+'conditionalFormatting', sqref='L2:M2001')
    for priority, style, formula in (
        ('2', '1', f'AND({fixed_term},L2="")'),
        ('3', '2', fixed_term),
        ('4', '0', f'L2="{DATE_NOT_REQUIRED}"'),
        ('5', '0', f'AND($A2<>"",$A2<>"{NEW_PERSON}")'),
    ):
        rule = ET.SubElement(dates_format, ns+'cfRule', type='expression', dxfId=style, priority=priority)
        ET.SubElement(rule, ns+'formula').text = formula
    root.insert(list(root).index(validations), dates_format)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)

def certificate_date_hint(row):
    return (f'IF(OR($F{row}="{LONG_VALIDITY}",AND($A{row}="{NEW_PERSON}",$F{row}="")),'
            f'"{DATE_NOT_REQUIRED}","")')

def certificate_date_formula(row, index):
    choice = f'$A{row}'
    lookup = f'SUBSTITUTE(SUBSTITUTE(SUBSTITUTE({choice},"~","~~"),"*","~*"),"?","~?")'
    value = f'VLOOKUP({lookup},\'人员选项\'!$A:$I,{index},FALSE)'
    return (f'IF(OR({choice}="",{choice}="{NEW_PERSON}"),{certificate_date_hint(row)},'
            f'IF($F{row}="{LONG_VALIDITY}","{DATE_NOT_REQUIRED}",'
            f'IFERROR(IF({value}=0,"",{value}),"")))')


def refresh_certificate_formulas(content):
    """Upgrade only known display formulas; preserve manually entered dates."""
    root = ET.fromstring(content)
    for cell in root.findall('s:sheetData/s:row/s:c', NS):
        ref = re.fullmatch(r'([LM])(\d+)', cell.get('r', ''))
        formula = cell.find('s:f', NS)
        if not ref or int(ref[2]) < 2 or formula is None:
            continue
        index = 8 if ref[1] == 'L' else 9
        if formula.text not in (certificate_date_hint(ref[2]), certificate_date_formula(ref[2], index)):
            continue
        formula.text = certificate_date_formula(ref[2], index)
        cell.attrib.pop('t', None)
        value = cell.find('s:v', NS)
        if value is not None:
            value.text = None
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def roster_values(state, grid, *, dated=False):
    if not grid:
        return [('已有人员（下拉来源，请勿修改）',), *((person_choice(p),) for p in state['people'])]
    rows = [('选择人员', *GRID_HEADERS[1:7]), (NEW_PERSON,)]
    if dated:
        rows[0] += ('证书有效开始', '证书有效结束')
    for person in state['people']:
        validity = '长期有效' if person.get('title_permanent') else ' 至 '.join(
            person[key] for key in ('title_from', 'title_to') if person.get(key)
        )
        proof = '已上传，请在网页查看' if person.get('certificate_id') else person.get('title_source') or '—'
        if dated and validity and not person.get('title_permanent'):
            validity = DATED_VALIDITY
        rows.append((person_choice(person), person['name'], person['code'], person.get('company') or '待补',
                     person.get('title') or '待补', validity or '待补', proof))
        if dated:
            rows[-1] += tuple(date.fromisoformat(person[key])
                              if person.get(key) and not person.get('title_permanent') else ''
                              for key in ('title_from', 'title_to'))
    return rows

def update_roster_xml(content, rows, *, epoch=False):
    # Preserve namespace prefixes and Excel/WPS compatibility attributes.
    doc = minidom.parseString(content)
    sheets = doc.getElementsByTagNameNS(SHEET_NS, 'sheetData')
    if not sheets:
        raise ValueError('人员选项工作表无效')
    data = sheets[0]
    for child in list(data.childNodes):
        data.removeChild(child)
    def append(parent, name, **attrs):
        prefix = data.prefix
        node = doc.createElementNS(SHEET_NS, f'{prefix}:{name}' if prefix else name)
        for key, value in attrs.items():
            node.setAttribute(key, value)
        parent.appendChild(node)
        return node
    if len(rows[0]) > 1:
        columns = doc.getElementsByTagNameNS(SHEET_NS, 'cols')
        if columns:
            for child in list(columns[0].childNodes):
                columns[0].removeChild(child)
            for i, width in enumerate((36, 14, 15, 22, 19, 25, 24, 22, 22)[:len(rows[0])], 1):
                append(columns[0], 'col', min=str(i), max=str(i), width=str(width), customWidth='1')
    for i, values in enumerate(rows, 1):
        row = append(data, 'row', r=str(i))
        for col, value in enumerate(values):
            if isinstance(value, date):
                cell = append(row, 'c', r=f'{chr(65+col)}{i}', s='10')
                serial = (value - (date(1904, 1, 1) if epoch else date(1899, 12, 30))).days
                append(cell, 'v').appendChild(doc.createTextNode(str(serial)))
            else:
                cell = append(row, 'c', r=f'{chr(65+col)}{i}', t='inlineStr')
                append(append(cell, 'is'), 't').appendChild(doc.createTextNode(value))
    dimensions = doc.getElementsByTagNameNS(SHEET_NS, 'dimension')
    if dimensions:
        dimensions[0].setAttribute('ref', f'A1:{chr(64+len(rows[0]))}{len(rows)}')
    return doc.toxml(encoding='utf-8')

def update_dropdown_xml(content, formula_text):
    doc = minidom.parseString(content)
    for rule in doc.getElementsByTagNameNS(SHEET_NS, 'dataValidation'):
        if rule.getAttribute('sqref').replace('$', '') == 'A2:A2001' and rule.getAttribute('type') == 'list':
            formulas = rule.getElementsByTagNameNS(SHEET_NS, 'formula1')
            if formulas:
                formula = formulas[0]
                for child in list(formula.childNodes):
                    formula.removeChild(child)
                formula.appendChild(doc.createTextNode(formula_text))
                return doc.toxml(encoding='utf-8')
    raise ValueError('未找到系统模板的人员下拉，请使用从系统下载的模板')

def workbook_strings(package):
    if 'xl/sharedStrings.xml' not in package.namelist():
        return []
    root = ET.fromstring(workbook_xml(package, 'xl/sharedStrings.xml'))
    return [''.join(item.itertext()) for item in root.findall('s:si', NS)]

def cell_value(cell, shared):
    typ = cell.get('t')
    value = cell.findtext('s:v', '', NS)
    if typ == 's':
        return shared[int(value)].strip()
    if typ == 'inlineStr':
        return ''.join(cell.find('s:is', NS).itertext()).strip()
    if typ == 'e':
        raise ValueError(f'单元格 {cell.get("r")} 含Excel错误')
    return value.strip()

def workbook_headers(package, content):
    shared = workbook_strings(package)
    for row in ET.fromstring(content).findall('s:sheetData/s:row', NS)[:2]:
        cells = {cell.get('r'): cell for cell in row.findall('s:c', NS)}
        number = row.get('r')
        header = [cell_value(cells[f'{col}{number}'], shared) if f'{col}{number}' in cells else ''
                  for col in 'ABCDEFGHIJKLM']
        while header and not header[-1]:
            header.pop()
        yield header

def active(e):
    return e.get('status') not in ('withdrawn','returned') and e.get('duplicate') != 'duplicate'

def project_flags(result):
    """Only assign entry findings and full-count windows to project selections."""
    ids = {f['entry_id'] for f in result['findings'] if f.get('entry_id')}
    ids.update(eid for w in result['windows'] if w['rank'] > 0 or w['missing_calendar'] for eid in w['entry_ids'])
    flags = {e['project_id'] for e in result['entries'] if e['id'] in ids}
    # The engine's multi-segment question is project-wide but has no entry id.
    for pid in {e['project_id'] for e in result['entries']}:
        spans = {(e.get('start'),e.get('end')) for e in result['entries'] if e['project_id']==pid and active(e)}
        if len(spans)>1: flags.add(pid)
    return flags

def export_options(state, person_id):
    result=next((r for r in analyze(state) if r['person']['id']==person_id),None)
    if not result: raise ValueError('人员不存在')
    flags=project_flags(result)
    pids={e['project_id'] for e in result['entries']}
    return dict(projects=[dict(id=p['id'],name=p['name'],code=p['code'],problem=p['id'] in flags,
                count=sum(e['project_id']==p['id'] for e in result['entries'])) for p in state['projects'] if p['id'] in pids],
                person_findings=[f for f in result['findings'] if not f.get('entry_id')])

def scoped_sections(state, revision, project_ids, person_id=None):
    projects={p['id']:p for p in state['projects']}
    if not project_ids or not set(project_ids)<=projects.keys(): raise ValueError('请选择有效项目')
    if person_id and person_id not in {p['id'] for p in state['people']}: raise ValueError('人员不存在')
    selected=set(project_ids)
    header=[['专家工时核查明细（模拟规则）'],['台账修订',revision,'规则版本',VERSION],
          ['导出时间（UTC）',datetime.now(timezone.utc).isoformat()],
          ['口径','按原始申报量筛查。常规范围不等于正式合理认定；金额差异不等于自动审减。'],
          ['导出项目','、'.join(projects[pid]['name'] for pid in project_ids)],
          ['申报明细'],
          ['人员','单位','工号','项目','项目编号','申报ID','投入开始','投入结束','申报数量','单位','折合工日',
           '参与状态','工期及实施期核查','申报单价','单价单位','申报金额（元）','依据单价','依据单位','按依据测算金额（元）',
           '单价差异金额（元）','职称与计费核查','合同或计价依据']]
    rows=[]; contexts=[]; person_notes=[]; participation=[]; claim_checks={}
    for r in analyze(state):
        if person_id and r['person']['id']!=person_id: continue
        entries=[e for e in r['entries'] if e['project_id'] in selected]
        if not entries: continue
        p=r['person']; ids={e['id'] for e in entries if active(e)}
        participation.append([p['name'],p.get('company',''),p['code'],len({e['project_id'] for e in r['entries']}),len({e['project_id'] for e in entries}),len(entries)])
        for e in entries:
            local=[f for f in r['findings'] if f.get('entry_id')==e['id']]
            def summary(category):
                fs=[f for f in local if (f['category']=='职称计费')==category]
                return '；'.join(f['message'] for f in fs) or ('已提供字段未见异常（模拟）' if active(e) else '不参与核查')
            money=lambda key,unit: round(e['amount']*e[key],2) if e.get('amount') is not None and e.get(key) is not None and e.get(unit)==e.get('unit') else None
            claimed=money('price','price_unit'); basis=money('basis_price','basis_unit')
            delta=round(claimed-basis,2) if claimed is not None and basis is not None else '待补或单位不同，未测算'
            windows=[w for w in r['windows'] if e['id'] in w['entry_ids'] and w['rank']>0]
            claim_checks[e['id']] = (
                local,
                max((w['rank'] for w in windows), default=0),
                any(w['missing_calendar'] and e['id'] in w['entry_ids'] for w in r['windows']),
            )
            schedule=summary(False)
            if windows: schedule+='；关联完整窗口预警（详见下表）'
            if not e.get('start') or not e.get('end'): schedule+='；日期待补'
            rows.append([p['name'],p.get('company',''),p['code'],projects[e['project_id']]['name'],projects[e['project_id']]['code'],e['id'],
                e.get('start',''),e.get('end',''),e.get('amount'),e.get('unit'),convert(e.get('amount'),e.get('unit'),state['config']) if convert(e.get('amount'),e.get('unit'),state['config']) is not None else '折算依据待补',
                '参与筛查' if active(e) else '撤回/退回/确认重复，不计入',schedule,e.get('price'),e.get('price_unit'),
                claimed if claimed is not None else '待补或数量与单价单位不同',e.get('basis_price'),e.get('basis_unit'),
                basis if basis is not None else '待补或数量与依据单位不同',delta,summary(True),e.get('basis_source','')])
        for w in r['windows']:
            if not ids.intersection(w['entry_ids']): continue
            contexts.append([p['name'],p['code'],w['start'],w['end'],w['demand'],w['c0'],w['c1'],w['c2'],w['label'],
                '、'.join(projects[pid]['name'] for pid in w['project_ids']), w['entry_ids'],
                '、'.join(map(str,w['missing_calendar'])) or '已维护'])
        for f in r['findings']:
            if not f.get('entry_id'): person_notes.append([p['name'],p['code'],f['category'],f['message'],p['id']])
    return header, rows, participation, contexts, person_notes, claim_checks

def scoped_report(state, revision, project_ids, person_id=None):
    header, claims, participation, contexts, person_notes, _ = scoped_sections(state, revision, project_ids, person_id)
    rows = header + claims
    rows += [[],['人员参与范围'],['人员','单位','工号','全部参与项目数','本次导出项目数','本次导出申报条数']]+participation
    rows += [[],['完整核查窗口（各窗口独立，不能相加；包含未选项目仅为跨项目背景）'],
             ['人员','工号','窗口开始','窗口结束','完整申报工日','常规容量','加班参考','高负荷参考','模拟等级','完整计入项目','完整计入申报ID','日历缺失年份']]
    rows += [[*context[:10], '、'.join(context[10]), context[11]] for context in contexts]
    rows += [[],['人员整体待核事项（不分配为某条申报结论）'],['人员','工号','类别','事项']]
    rows += [note[:4] for note in person_notes]
    buf=io.StringIO(); writer=csv.writer(buf)
    for row in rows:
        writer.writerow([("'"+v if isinstance(v,str) and (v.lstrip().startswith(('=','+','-','@')) or v.startswith(('\t','\r','\n'))) else v) for v in row])
    return buf.getvalue().encode('utf-8-sig')

def read_xlsx(encoded):
    raw = decode_xlsx(encoded)
    try:
        with ZipFile(io.BytesIO(raw)) as z:
            check_xlsx_package(z)
            def xml(path):
                return ET.fromstring(workbook_xml(z, path))
            wb=xml('xl/workbook.xml')
            target=worksheet_path(wb, xml('xl/_rels/workbook.xml.rels'), '人员工时')
            shared=workbook_strings(z)
            values=[]
            has_hint_column = False
            grid = False
            dated_grid = False
            for row in xml(target).findall('s:sheetData/s:row',NS):
                rownum = int(row.get('r','0'))
                cells={}
                for c in row.findall('s:c',NS):
                    ref=c.get('r',''); m=re.fullmatch(r'([A-Z]{1,3})(\d+)',ref)
                    if not m: raise ValueError('Excel 单元格地址无效')
                    col=0
                    for ch in m[1]: col=col*26+ord(ch)-64
                    # The generated hint is display-only. A formula or its
                    # cached value here must not turn an empty row into a claim.
                    if col>len(FIELDS) or (has_hint_column and rownum>1 and col==9): continue
                    formula = c.find('s:f',NS)
                    if formula is not None:
                        # Ignore displayed roster results, including Excel's shared formulas.
                        # Identity and qualification are resolved again against the current ledger.
                        if grid and 2 <= col <= 7:
                            continue
                        if dated_grid and col in (12, 13) and (
                            formula.text == certificate_date_hint(rownum) or
                            formula.text == certificate_date_formula(rownum, col-4) or
                            (formula.get('t') == 'shared' and not formula.text)
                        ):
                            continue
                        if not values:
                            raise ValueError(f'表头单元格 {ref} 不能使用公式')
                        cells[col-1] = '=' + (formula.text or '')
                        cells.setdefault(-1, []).append((col-1, '请填写实际值', 'formula'))
                        continue
                    if values and c.get('t') == 'e':
                        cells[col-1] = c.findtext('s:v', '', NS)
                        cells.setdefault(-1, []).append((col-1, 'Excel 单元格错误，请重新填写', 'cell'))
                        continue
                    cells[col-1]=cell_value(c,shared)
                if not values:
                    has_hint_column = [cells.get(i,'') for i in range(len(COMPACT_HINT_HEADERS))] == COMPACT_HINT_HEADERS
                    dated_grid = is_dated_grid(cells)
                    grid = dated_grid or [cells.get(i,'') for i in range(len(GRID_FIELDS))] in (GRID_HEADERS,GRID_REFERENCE_HEADERS)
                if any(cells.values()): values.append((rownum,cells))
                if len(values)>2001: raise ValueError('一次最多导入2000条申报')
            epoch=bool(wb.find('s:workbookPr',NS) is not None and wb.find('s:workbookPr',NS).get('date1904') in ('1','true'))
            return values,epoch
    except (BadZipFile,KeyError,ET.ParseError,IndexError,TypeError):
        raise ValueError('无法读取Excel，请使用有效的.xlsx模板文件')

def is_dated_grid(cells):
    return [cells.get(i,'') for i in range(len(DATED_GRID_FIELDS))] == DATED_GRID_HEADERS

def import_preview(state, encoded, defaults=None):
    sheet,epoch=read_xlsx(encoded)
    if not sheet: raise ValueError('Excel 为空')
    expected=[label for label,_ in FIELDS]
    compact=[sheet[0][1].get(i,'') for i in range(len(COMPACT_FIELDS))]==[label for label,_ in COMPACT_FIELDS]
    compact = compact or [sheet[0][1].get(i,'') for i in range(len(COMPACT_HINT_HEADERS))] == COMPACT_HINT_HEADERS
    dated_grid = is_dated_grid(sheet[0][1])
    grid = dated_grid or [sheet[0][1].get(i,'') for i in range(len(GRID_FIELDS))] in (GRID_HEADERS,GRID_REFERENCE_HEADERS)
    if not (grid or compact) and [sheet[0][1].get(i,'') for i in range(len(FIELDS))]!=expected:
        raise ValueError('表头与模板不一致，请保留列名及顺序')
    layout = 'dated' if dated_grid else 'grid' if grid else 'compact' if compact else 'legacy'
    return validate_import_rows(state, sheet[1:], defaults, layout, epoch)

IMPORT_LAYOUTS = {'dated': DATED_GRID_FIELDS, 'grid': GRID_FIELDS, 'compact': COMPACT_FIELDS, 'legacy': FIELDS}

def export_import_problems(template, state, payload):
    layout = payload.get('layout')
    records = payload.get('rows')
    if not isinstance(layout, str) or layout not in IMPORT_LAYOUTS or not isinstance(records, list) or not 1 <= len(records) <= 2000:
        raise ValueError('请选择有效的待修改行')
    fields = IMPORT_LAYOUTS[layout]
    raw = selection_template(template, state)
    out = io.BytesIO()
    ns = '{' + SHEET_NS + '}'
    with ZipFile(io.BytesIO(raw)) as source, ZipFile(out, 'w', ZIP_DEFLATED) as target:
        for item in source.infolist():
            content = source.read(item)
            if item.filename == 'xl/worksheets/sheet1.xml':
                root = ET.fromstring(content)
                data = root.find('s:sheetData', NS)
                data.clear()
                all_rows = [{key:label for label,key in fields}] + records
                for number, record in enumerate(all_rows, 1):
                    if not isinstance(record, dict) or not all(isinstance(value, str) for value in record.values()):
                        raise ValueError('待修改行内容无效')
                    row = ET.SubElement(data, ns+'row', r=str(number))
                    for col, (_, key) in enumerate(fields):
                        cell = ET.SubElement(row, ns+'c', r=f'{chr(65+col)}{number}',
                                             t='inlineStr', s='4' if number == 1 else '6')
                        ET.SubElement(ET.SubElement(cell, ns+'is'), ns+'t').text = record.get(key, '')
                for tag in ('dataValidations', 'conditionalFormatting'):
                    if layout != 'dated':
                        for element in root.findall('s:'+tag, NS):
                            root.remove(element)
                content = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            target.writestr(item, content)
    return out.getvalue()
FIELD_LABELS = {key: label for label, key in FIELDS}
FIELD_LABELS.update(person_choice='选择人员', validity='有效期')
FIELD_LABELS.update(start='投入开始', end='投入结束', title_from='证书有效开始', title_to='证书有效结束')

class ImportRowIssue(ValueError):
    def __init__(self, issues):
        super().__init__('；'.join(issue['message'] for issue in issues))
        self.issues = issues

def repair_import_row(state, payload):
    layout, row, data, epoch = (payload.get(k) for k in ('layout', 'row', 'data', 'epoch'))
    if not isinstance(layout, str) or layout not in IMPORT_LAYOUTS or type(row) is not int or not 1 <= row <= 1048576 or type(epoch) is not bool:
        raise ValueError('Excel 行标识无效')
    fields = IMPORT_LAYOUTS[layout]
    if not isinstance(data, dict) or set(data) != {key for _, key in fields} or not all(isinstance(v, str) for v in data.values()):
        raise ValueError('Excel 行填写内容无效')
    return validate_import_rows(state, [(row, {i: data[key].strip() for i, (_, key) in enumerate(fields)})],
                                payload.get('defaults'), layout, epoch)

def validate_import_rows(state, sheet_rows, defaults, layout, epoch):
    fields = IMPORT_LAYOUTS[layout]
    dated_grid = layout == 'dated'
    grid = layout in ('dated', 'grid')
    compact = layout == 'compact'
    defaults=defaults or {}
    if not isinstance(defaults,dict): raise ValueError('公共信息格式错误')
    allowed={key for _,key in FIELDS if key not in PERSON_KEYS}|{'company'}
    if any(key not in allowed for key in defaults): raise ValueError('不支持的公共字段')
    existing={(p.get('company',''),p['code']):p for p in state['people']}
    identities={}; rows=[]; errors=[]
    for rownum,cells in sheet_rows:
        field = 'person_choice' if (grid or compact) else 'code'
        def issue(key, message):
            return dict(field=key, message=message)
        try:
            explicit={key:cells.get(i,'') for i,(_,key) in enumerate(fields)}
            if dated_grid:
                for key in ('title_from', 'title_to'):
                    if explicit[key] == DATE_NOT_REQUIRED:
                        explicit[key] = ''
            cell_issues = [dict(field=fields[i][1], message=message, replace=True)
                           for i,message,_ in cells.get(-1, []) if i < len(fields)]
            if cell_issues:
                raise ImportRowIssue(cell_issues)
            data={key:'' for _,key in FIELDS}
            data.update({k:str(v).strip() for k,v in defaults.items() if v is not None})
            data.update({k:v for k,v in explicit.items() if v!=''})
            inherited=[k for k in defaults if defaults[k] is not None and str(defaults[k]).strip() and not explicit.get(k)]
            choice = data.get('person_choice')
            if grid and choice == NEW_PERSON:
                validity = data.get('validity', '')
                if dated_grid:
                    field = 'validity'
                    if validity == DATED_VALIDITY:
                        if not data['title_from'] or not data['title_to']:
                            raise ImportRowIssue([issue(key, f'请填写{FIELD_LABELS[key]}')
                                                  for key in ('title_from','title_to') if not data[key]])
                    elif validity in ('', LONG_VALIDITY):
                        if data['title_from'] or data['title_to']:
                            raise ValueError('已填写证书日期，请在有效期列选择“固定时间段内有效”')
                    else:
                        raise ValueError('请从有效期下拉中选择长期有效或固定时间段内有效')
                elif validity and validity != LONG_VALIDITY:
                    period = re.fullmatch(r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*至\s*(\d{4}[/-]\d{1,2}[/-]\d{1,2})', validity)
                    if not period:
                        raise ValueError('有效期请填写“长期有效”或“2025/4/4 至 2026/4/4”')
                    data['title_from'], data['title_to'] = (value.replace('-', '/') for value in period.groups())
            elif (grid or compact) and choice:
                matches=[p for p in state['people'] if person_choice(p)==data['person_choice']]
                if len(matches)!=1: raise ValueError('人员选择已失效或不唯一，请重新下载模板选择，不按姓名猜测')
                chosen=matches[0]
                for key in ('name','company','code'):
                    if explicit.get(key) and explicit[key]!=chosen.get(key):
                        field = key
                        raise ValueError(f'{FIELD_LABELS[key]}与所选人员不一致，请清空该格或重新选择人员')
                data.update({k:chosen.get(k,'') for k in PERSON_KEYS})
                inherited=[k for k in inherited if k not in PERSON_KEYS]
            elif grid:
                raise ValueError('请在第一列选择已有人员或“新增人员”')
            issues = []
            for k in sorted(DATE_KEYS):
                if not data[k]: continue
                try:
                    data[k] = parse_import_date(data[k], epoch)
                except (ValueError, OverflowError):
                    issues.append(issue(k, f'{FIELD_LABELS[k]}须为有效日期，例如 2025/4/4'))
            for k in sorted(NUMBER_KEYS):
                if data[k]=='': data[k]=None; continue
                try:
                    data[k]=float(data[k])
                    if not math.isfinite(data[k]) or data[k]<0:
                        raise ValueError()
                except ValueError:
                    issues.append(issue(k, f'{FIELD_LABELS[k]}须为非负数字'))
            for k in ('name','code','start','end','unit','amount'):
                if data[k] is None or data[k] == '':
                    issues.append(issue(k, f'请填写{FIELD_LABELS[k]}'))
            if dated_grid and choice == NEW_PERSON:
                if not data['company']:
                    issues.append(issue('company', '请填写新人员的所属单位'))
                if not data['title']:
                    issues.append(issue('title', '请填写新人员的职称'))
                elif data['title'] not in QUALIFICATION_LEVELS:
                    issues.append(issue('title', '职称请选择技术专家、项目经理、高级技术人员或一般技术人员'))
            if data['amount'] == 0:
                issues.append(issue('amount', '申报数量须大于0'))
            for k in ('unit','price_unit','basis_unit'):
                allowed_units = ('工日','工时')
                if data[k] and data[k] not in allowed_units:
                    issues.append(issue(k, f'{FIELD_LABELS[k]}仅支持' + '、'.join(allowed_units)))
            for a,b in [('start','end'),('title_from','title_to'),('basis_from','basis_to')]:
                if not data[a] or not data[b] or any(item['field'] in (a,b) for item in issues):
                    continue
                if data[a]>data[b] or (date.fromisoformat(data[b])-date.fromisoformat(data[a])).days>3660:
                    issues.append(issue(b, f'{FIELD_LABELS[b]}不能早于开始日期，期间最多10年'))
            if issues:
                raise ImportRowIssue(issues)
            field = 'code'
            identity=(data['company'],data['code']); person=existing.get(identity)
            if grid and choice == NEW_PERSON and person:
                raise ValueError('同单位工号已在库，请在第一列选择已有人员')
            if not data['company'] and not person:
                same_code=[p for p in state['people'] if p['code']==data['code']]
                if same_code: raise ValueError('工号已存在，请使用人员下拉选择或补充所属单位')
            if person and person['name']!=data['name']: raise ValueError('同单位工号对应的姓名与台账不一致')
            old=identities.get(identity)
            if old and any(old.get(k)!=data.get(k) for k in PERSON_KEYS): raise ValueError('同单位工号在文件中人员信息不一致')
            if person and any(data.get(k) and data[k]!=person.get(k) for k in PERSON_KEYS):
                raise ValueError('已有人员资料与模板不一致，请先在人员页核对，导入不会覆盖')
            identities[identity]=data
            rows.append(dict(row=rownum,data=data,person_id=person['id'] if person else None,inherited=inherited))
        except (ValueError,OverflowError) as exc:
            issues = exc.issues if isinstance(exc, ImportRowIssue) else [issue(field, str(exc))]
            errors.append(dict(row=rownum, message=str(exc), issues=issues, data=explicit))
    if not rows and not errors: errors.append(dict(row=2,message='请至少填写一条申报'))
    return dict(rows=rows, errors=errors, layout=layout, epoch=epoch,
                fields=[dict(key=key, label=label) for label,key in fields],
                new_people=len([i for i in identities if i not in existing]))

def parse_import_date(value, epoch):
    if re.fullmatch(r'\d+(\.0+)?', value):
        origin = date(1904,1,1) if epoch else date(1899,12,30)
        value = (origin + timedelta(days=int(float(value)))).isoformat()
    slash_date = re.fullmatch(r'(\d{4})/(\d{1,2})/(\d{1,2})', value)
    if slash_date:
        y,m,d = map(int, slash_date.groups())
        result = date(y,m,d)
    elif re.fullmatch(r'\d{4}-\d{2}-\d{2}(T00:00:00(?:\.000)?Z?)?', value):
        result = date.fromisoformat(value[:10])
    else:
        result = date.fromisoformat(value)
    if not 2000 <= result.year <= 2100:
        raise ValueError()
    return result.isoformat()
