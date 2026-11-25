"""A4 review exports using the approved result-first table template."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from os import environ
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engine import VERSION, LABELS, analyze, convert, prepare_entry, review_person
from project_io import active, scoped_sections


def register_report_font():
    configured = environ.get('EXPERT_HOURS_PDF_FONT')
    windows_fonts = Path(environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    candidates = [Path(configured)] if configured else [
        windows_fonts / 'msyh.ttc', windows_fonts / 'NotoSansSC-VF.ttf',
        Path('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'),
    ]
    for path in candidates:
        if path.is_file():
            pdfmetrics.registerFont(TTFont('ReportChinese', str(path)))
            return 'ReportChinese'
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    return 'STSong-Light'


FONT = register_report_font()
BOLD = FONT
bold_path = Path(environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyhbd.ttc'
if bold_path.is_file() and not environ.get('EXPERT_HOURS_PDF_FONT'):
    pdfmetrics.registerFont(TTFont('ReportChineseBold', str(bold_path)))
    BOLD = 'ReportChineseBold'
INK = colors.HexColor('#203246')
ACCENT = colors.HexColor('#24547B')
MUTED = colors.HexColor('#657180')
LINE = colors.HexColor('#DDE3E9')
PALE = colors.HexColor('#F3F5F7')
RED = colors.HexColor('#B42318')
GREEN = colors.HexColor('#4D7567')
RISK_COLORS = (colors.HexColor('#23764D'), colors.HexColor('#8A650D'), RED, colors.HexColor('#7B2CBF'))
MARGIN = 40
WIDTH = A4[0] - MARGIN * 2 - 12


def quantity(value):
    return f'{value:,.2f}'.rstrip('0').rstrip('.') if isinstance(value, (int, float)) else value


def unit_label(unit):
    return unit if unit in ('工日', '工时') else '单位待更正'


def date_span(start, end):
    if start and start == end:
        return str(start)
    return f'{start or "待补"} 至 {end or "待补"}'



def report_assessments(state, project_ids, person_id=None, *, include_empty=False):
    """Assess each selected person locally by project and across the whole ledger."""
    selected = set(project_ids)
    assessments = []
    for full in analyze(state):
        person = full['person']
        if person_id and person['id'] != person_id:
            continue
        exported = [e for e in full['entries'] if e['project_id'] in selected]
        if not exported and not include_empty:
            continue
        local_results = []
        for pid in dict.fromkeys(e['project_id'] for e in exported):
            local_state = {**state, 'entries': [e for e in exported if e['project_id'] == pid]}
            local_results.append(review_person(person, local_state))
        project_results = dict(zip(dict.fromkeys(e['project_id'] for e in exported), local_results))
        local_windows = [w for result in local_results for w in result['windows']]
        local_findings = [f for result in local_results for f in result['findings']]
        local_active = [e for e in exported if active(e)]
        full_active = [e for e in full['entries'] if active(e)]
        missing_calendar = any(w['missing_calendar'] for w in full['windows'])
        if not local_active:
            status = 'excluded'
        elif any(w['rank'] > 0 for w in full['windows']) or any(f['level'] == 'warning' for f in full['findings']):
            status = 'review'
        elif missing_calendar or full['findings']:
            status = 'pending'
        else:
            status = 'pass'
        assessments.append(dict(person=person, exported=exported, local_entries=local_active,
                                local_windows=local_windows, local_findings=local_findings,
                                full=full, full_entries=full_active, status=status, project_results=project_results))
    return assessments



def paragraph(value, size=10, color=INK, *, bold=False, after=0, keep=False, highlight=True):
    style = ParagraphStyle('report', fontName=BOLD if bold else FONT, fontSize=size,
                           leading=size * 1.5, textColor=color, wordWrap='CJK',
                           spaceAfter=after, keepWithNext=keep)
    lines = str(value if value not in (None, '') else '待补').split('\n')
    # Only overload statements are red within problem descriptions.
    rendered = []
    for line in lines:
        text = escape(line)
        if highlight and '超参考' in line and '未超' not in line:
            text = f'<font color="{RED.hexval().replace("0x", "#")}">{text}</font>'
        rendered.append(text)
    return Paragraph('<br/>'.join(rendered), style)


def heading(text):
    return paragraph(text, 12, ACCENT, bold=True, after=8, keep=True)


def table(headers, rows, weights, *, title=None):
    widths = [WIDTH * weight / sum(weights) for weight in weights]
    cells = [[paragraph(text, 9.5, ACCENT, bold=True) for text in headers]]
    cells += [[text if isinstance(text, Paragraph) else paragraph(text, 9.5) for text in row] for row in rows]
    header = 0
    if title:
        cells.insert(0, [paragraph(title, 12, ACCENT, bold=True)] + [''] * (len(headers) - 1))
        header = 1
    result = LongTable(cells, colWidths=widths, repeatRows=(header,), hAlign='LEFT', splitInRow=1)
    style = [
        ('BACKGROUND', (0, header), (-1, header), PALE),
        ('LINEBELOW', (0, header), (-1, -1), .45, LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
    ]
    if title:
        style.extend([('SPAN', (0, 0), (-1, 0)), ('LEFTPADDING', (0, 0), (-1, 0), 0),
                      ('TOPPADDING', (0, 0), (-1, 0), 0), ('BOTTOMPADDING', (0, 0), (-1, 0), 8)])
    result.setStyle(TableStyle(style))
    return result


def reference(window, config):
    rank = window['rank']
    base = [window['c0'], window['c0'], window['c1'], window['c2']][rank]
    return base + config['tolerance']


def flagged_windows(result):
    return [w for w in result['windows'] if w['rank'] > 0]


def total_days(entries, config):
    values = [convert(e.get('amount'), e.get('unit'), config) for e in entries if active(e)]
    if not values or any(value is None for value in values):
        return None
    return sum(values)


def capacity_cell(entries, windows, state, *, summary_only=False):
    valid = [e for e in entries if active(e)]
    if not valid:
        return paragraph('暂无有效申报', 9.5, MUTED)
    projects = {p['id']: p for p in state['projects']}
    incomplete = any(not (e.get('start') and e.get('end')) or
                     prepare_entry(e, projects[e['project_id']], state['config'])[1] for e in valid)
    calendar_missing = any(w['missing_calendar'] for w in windows)
    worst = max(windows, key=lambda w: (w['rank'], w['ratio']), default=None)
    if worst and worst['rank'] > 0:
        if summary_only:
            return paragraph(LABELS[worst['rank']] + ('\n暂估，资料待补' if incomplete or calendar_missing else ''), 9.5, RISK_COLORS[worst['rank']])
        limit = reference(worst, state['config'])
        note = '\n日期或日历待补，暂估' if incomplete or calendar_missing else ''
        return paragraph(f'{date_span(worst["start"], worst["end"])}\n'
                         f'该段 {quantity(worst["demand"])} 工日 / 参考 {quantity(limit)}\n{LABELS[worst["rank"]]}，需核查{note}', 9.5, RISK_COLORS[worst['rank']])
    if incomplete or calendar_missing or not worst:
        notes = ['资料待补，工时暂不能判断']
        if incomplete:
            notes.append('日期、数量或原单位需核实')
        if calendar_missing:
            notes.append('工作日历待补')
        return paragraph('\n'.join(notes), 9.5)
    return paragraph(LABELS[0] if summary_only else
                     f'合计 {quantity(total_days(valid, state["config"]))} 工日\n{LABELS[0]}', 9.5, RISK_COLORS[0])


def problem_labels(findings):
    labels = []
    schedule = [f for f in findings if f['category'] == '实施期' and
                not f['message'].startswith('本条投入超过')]
    date_warning = any(f['level'] == 'warning' for f in schedule)
    if date_warning:
        labels.append('投入日期需核对')
    if any(f['category'] == '职称计费' for f in findings):
        labels.append('职称或计费资料需核对')
    if not date_warning and any(f['level'] == 'pending' for f in schedule):
        labels.append('实施期依据或投入日期待补')
    if any('换算' in f['message'] or '更正单位' in f['message'] for f in findings):
        labels.append('数量或原单位需核实')
    if any('重复' in f['message'] or '多段申报' in f['message'] for f in findings):
        labels.append('多笔申报依据待核')
    return labels


def assessment_reasons(assessment, *, local_label='本项目'):
    if not assessment['local_entries']:
        return ['暂无有效申报']
    reasons = []
    if any(w['rank'] > 0 for w in assessment['local_windows']):
        reasons.append(local_label + '工时超参考')
    if flagged_windows(assessment['full']):
        reasons.append('全库工时超参考')
    reasons += problem_labels(assessment['full']['findings'])
    if any(w['missing_calendar'] for w in assessment['full']['windows']):
        reasons.append('工作日历待补')
    if not reasons:
        reasons.append('资料待补' if assessment['status'] == 'pending' else '未发现异常')
    return reasons


def overview_card(assessments, fact):
    counts = {key: sum(a['status'] == key for a in assessments)
              for key in ('review', 'pending', 'pass', 'excluded')}
    if counts['review']:
        verdict, color, background = '发现问题，需核查', RED, colors.HexColor('#FFF4DE')
    elif counts['pending']:
        verdict, color, background = '资料待补，暂无法判断是否合格', RED, colors.HexColor('#FFF4DE')
    elif counts['pass']:
        verdict, color, background = '核查通过（模拟）', GREEN, colors.HexColor('#EEF5F1')
    else:
        verdict, color, background = '暂无有效申报', MUTED, PALE
    labels = [('review', '人需核查'), ('pending', '人待补资料'),
              ('pass', '人核查通过'), ('excluded', '人暂无有效申报')]
    tally = '  ·  '.join(f'{counts[key]} {label}' for key, label in labels if counts[key])
    if not assessments:
        tally = '当前台账暂无人员记录'
    result = Table([[paragraph('核查结论（模拟）', 9, MUTED)],
                    [paragraph(verdict, 20, color, bold=True)],
                    [paragraph(tally, 10)], [paragraph(fact, 9.5, MUTED)]],
                   colWidths=[WIDTH], hAlign='LEFT')
    result.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), background),
        ('LEFTPADDING', (0, 0), (-1, -1), 14),
        ('RIGHTPADDING', (0, 0), (-1, -1), 14),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 10),
    ]))
    return result


def verification_notes(assessments, state):
    people_by_issue = {}
    for assessment in assessments:
        if not assessment['local_entries']:
            continue
        name = f'{assessment["person"]["name"]}（{assessment["person"]["code"]}）'
        for reason in assessment_reasons(assessment):
            if reason == '未发现异常' or '超参考' in reason:
                continue
            if reason == '实施期依据或投入日期待补':
                reason = '投入日期需核对'
            people_by_issue.setdefault(reason, []).append(name)
    actions = {
        '投入日期需核对': '对照人员投入记录和项目文件，核实投入日期与项目实施期，补齐起止日期及确认依据。',
        '职称或计费资料需核对': '核对职称证明、有效期、计费等级、单价及适用的合同依据。',
        '数量或原单位需核实': '对照原始资料补齐数量，更正为工日或工时；资料不足的记录暂未计入工时。',
        '多笔申报依据待核': '核对同项目多笔申报的分段、追加或重复依据。',
        '工作日历待补': '补齐涉及年份的节假日与调休日历后重新核查。',
        '资料待补': '补齐申报及证明资料后重新核查。',
    }
    notes = []
    active_people = {f'{a["person"]["name"]}（{a["person"]["code"]}）' for a in assessments if a['local_entries']}
    for issue, people in people_by_issue.items():
        names = list(dict.fromkeys(people))
        prefix = '' if len(assessments) == 1 else ('全部有效申报人员：' if set(names) == active_people else '、'.join(names) + '：')
        notes.append(prefix + actions[issue])
    if not notes:
        if any(a['status'] == 'review' for a in assessments):
            notes.append('对照原始工时记录，核实上表超参考时段的数量、日期和加班依据。')
        elif any(a['status'] == 'pass' for a in assessments):
            notes.append('当前提供的资料未发现其他待核事项。')
    return [heading('待核实'), *[paragraph(note, 10, after=4, highlight=False) for note in notes]] if notes else []


def project_rows(assessments, state):
    return [[f'{a["person"]["name"]}\n{a["person"]["code"]}',
             capacity_cell(a['local_entries'], a['local_windows'], state),
             capacity_cell(a['full_entries'], a['full']['windows'], state),
             paragraph('\n'.join(assessment_reasons(a)), 9.5)] for a in assessments]


def personnel_project_rows(assessment, state):
    projects = {p['id']: p for p in state['projects']}
    rows = []
    for pid, result in assessment['project_results'].items():
        entries = [e for e in result['entries'] if active(e)]
        periods = list(dict.fromkeys((e.get('start'), e.get('end')) for e in entries))
        dates = '；'.join(date_span(start, end) for start, end in periods) or '暂无有效投入期'
        label = f'{projects[pid]["name"]}\n（投入 {dates}）'
        quantities = {}
        for entry in entries:
            unit = entry.get('unit')
            if entry.get('amount') is None or unit not in ('工日', '工时'):
                continue
            quantities[unit] = quantities.get(unit, 0) + entry['amount']
        declared = '、'.join(f'{quantity(value)} {unit}' for unit, value in quantities.items())
        missing_quantity = any(e.get('amount') is None or e.get('unit') not in ('工日', '工时') for e in entries)
        if not entries:
            declared = '本次不参与核查'
        elif missing_quantity:
            declared = '数量或原单位待核实\n暂未计入工时' if not declared else declared + '\n另有记录资料待补'
        elif any(e.get('unit') != '工日' for e in entries):
            declared += f'\n折合 {quantity(total_days(entries, state["config"]))} 工日'
        warnings = flagged_windows(result)
        if warnings:
            rank = max(w['rank'] for w in warnings)
            check = paragraph(LABELS[rank] + '\n需核查', 9.5, RISK_COLORS[rank])
        elif not entries:
            check = paragraph('暂无有效申报', 9.5, MUTED)
        elif any(not (e.get('start') and e.get('end')) for e in entries) or missing_quantity or any(w['missing_calendar'] for w in result['windows']):
            check = paragraph('资料待补，暂不能判断', 9.5)
        else:
            check = paragraph(LABELS[0], 9.5, RISK_COLORS[0])
        issues = problem_labels(result['findings'])
        rows.append([label, paragraph(declared, 9.5, RED if warnings else INK), check,
                     '\n'.join(issues) if issues else '未发现其他问题'])
    return rows


def window_table(assessment, state):
    windows = flagged_windows(assessment['full'])
    if not windows:
        return []
    rows = []
    for window in windows:
        limit = reference(window, state['config'])
        excess = max(0, window['demand'] - limit)
        provisional = bool(window['missing_calendar']) or any(
            not (e.get('start') and e.get('end')) for e in assessment['full_entries'] if e['id'] in window['entry_ids'])
        result = f'{LABELS[window["rank"]]}\n超出 {quantity(excess)} 工日' + ('\n暂估，资料待补' if provisional else '')
        rows.append([date_span(window['start'], window['end']), paragraph(f'{quantity(window["demand"])} 工日', 9.5, RED),
                     f'{quantity(limit)} 工日', paragraph(result, 9.5, RISK_COLORS[window['rank']])])
    return [table(['核查日期', '完整申报累计', '该段参考', '结果'], rows, [205, 100, 100, 110],
                  title='全库累计需要核查的时段'), Spacer(1, 12)]


def report_content(state, project_ids, assessments, person_id=None, *, overview=False):
    projects = {p['id']: p for p in state['projects']}
    claim_count = sum(len(a['exported']) for a in assessments)
    if overview:
        title, subject = '人员核查结果总表', '当前台账全部人员'
        meta = f'{len(state["people"])} 人 · {len(state["projects"])} 个项目 · {len(state["entries"])} 笔申报'
        time_count = sum(bool(flagged_windows(a['full'])) for a in assessments)
        fact = f'{time_count} 人存在全库工时超参考；逐人核查意见见下表。'
    elif person_id:
        a = assessments[0]
        person = a['person']
        title, subject = '人员工时核查报告', f'{person["name"]}（{person["code"]}）'
        meta = f'本次 {len(set(project_ids))} 个项目 · {claim_count} 笔申报 · 库内共 {len({e["project_id"] for e in a["full_entries"]})} 个有效项目'
        windows = flagged_windows(a['full'])
        fact = f'全库工时超参考，共 {len(windows)} 个时段需核查。' if windows else '全库工时逐时段核查，结果及其他待核事项见下表。'
    else:
        title = '项目工时核查报告'
        subject = '、'.join(projects[pid]['name'] for pid in dict.fromkeys(project_ids))
        meta = f'本次 {len(assessments)} 人 · {claim_count} 笔申报'
        if len(set(project_ids)) == 1:
            p = projects[project_ids[0]]
            meta = f'项目 {p["code"]} · 实施期 {date_span(p.get("impl_start"), p.get("impl_end"))} · {len(assessments)} 人'
        time_count = sum(bool(flagged_windows(a['full'])) for a in assessments)
        fact = f'{time_count} 人存在全库工时超参考；本项目工时及其他问题分别见下表。'
    content = [paragraph(title, 22, ACCENT, bold=True, after=11),
               paragraph(subject, 15, bold=True, after=7), paragraph(meta, 9.5, MUTED, after=15),
               overview_card(assessments, fact), Spacer(1, 18)]
    if person_id:
        content.extend([table(['项目', '申报数量', '工时判断', '其他问题'],
                              personnel_project_rows(assessments[0], state), [180, 85, 110, 140],
                              title='各项目单独看'), Spacer(1, 15)])
        content.extend(window_table(assessments[0], state))
        other_projects = [p for p in state['projects'] if p['id'] not in project_ids and
                          any(e['project_id'] == p['id'] for e in assessments[0]['full_entries'])]
        if other_projects:
            content.append(paragraph('全库另计项目：' + '、'.join(f'{p["name"]}（{p["code"]}）' for p in other_projects), 9, MUTED, after=10))
    elif overview:
        rows = [[f'{a["person"]["name"]}\n{a["person"]["code"]}',
                 str(len({e['project_id'] for e in a['full_entries']})),
                 capacity_cell(a['full_entries'], a['full']['windows'], state, summary_only=True),
                 paragraph('\n'.join(assessment_reasons(a, local_label='单项目')), 9.5)] for a in assessments]
        if rows:
            content.extend([table(['人员', '项目数', '全库工时', '核查结论 / 原因'], rows,
                                  [105, 55, 155, 200], title='按人员汇总'), Spacer(1, 15)])
    else:
        local_label = '本项目工时' if len(set(project_ids)) == 1 else '所选项目工时'
        content.extend([table(['人员', local_label, '全库累计', '主要问题'], project_rows(assessments, state),
                              [85, 110, 155, 165], title='每个人的结果'), Spacer(1, 15)])
    content.extend(verification_notes(assessments, state))
    content.extend([Spacer(1, 13), paragraph('工日按当前规则折算；各时段分别比较，累计行之间不可相加。模拟核查结论供业务人员确认。', 9, MUTED)])
    return title, content


def review_pdf(state, revision, project_ids, person_id=None, *, demo=False):
    _, claims, _, _, _, _ = scoped_sections(state, revision, project_ids, person_id)
    if not claims:
        raise ValueError('所选范围没有申报记录')
    assessments = report_assessments(state, project_ids, person_id)
    title, content = report_content(state, project_ids, assessments, person_id)
    return build_report(content, title, revision, demo)


def overview_pdf(state, revision, *, demo=False):
    project_ids = [p['id'] for p in state['projects']]
    assessments = report_assessments(state, project_ids, include_empty=True)
    title, content = report_content(state, project_ids, assessments, overview=True)
    return build_report(content, title, revision, demo)


def build_report(content, title, revision, demo):
    mode = '模拟台账' if demo else '实际台账'
    generated = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    footer = f'{mode} · 模拟规则 {VERSION} · 台账修订 {revision} · {generated}（北京时间）'

    def page(canvas, doc):
        canvas.setStrokeColor(LINE)
        canvas.line(MARGIN, 37, A4[0] - MARGIN, 37)
        canvas.setFont(FONT, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 22, footer)
        canvas.drawRightString(A4[0] - MARGIN, 22, f'第 {doc.page} 页')

    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, title=title, author='专家工时核验',
                            leftMargin=MARGIN, rightMargin=MARGIN, topMargin=35, bottomMargin=49)
    doc.build(content, onFirstPage=page, onLaterPages=page)
    return output.getvalue()
