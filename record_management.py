"""Reversible removal of ledger records, including their dependent claims."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

KINDS = {'projects': '项目', 'people': '人员', 'entries': '申报'}


def validate_deleted_records(state):
    items = state.get('deleted_records', [])
    if not isinstance(items, list):
        raise ValueError('已删除记录格式错误')
    seen = set()
    for item in items:
        if not isinstance(item, dict) or item.get('kind') not in KINDS:
            raise ValueError('已删除记录类型无效')
        identity, record, entries = item.get('id'), item.get('record'), item.get('entries')
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError('已删除记录编号缺失或重复')
        seen.add(identity)
        if not isinstance(record, dict) or not isinstance(record.get('id'), str) or not record['id']:
            raise ValueError('已删除记录内容缺失')
        if not isinstance(entries, list) or not all(isinstance(e, dict) and isinstance(e.get('id'), str) and e['id'] for e in entries):
            raise ValueError('已删除申报格式错误')
        if len({e['id'] for e in entries}) != len(entries):
            raise ValueError('已删除申报编号重复')
        if 'position' in item and (type(item['position']) is not int or item['position'] < 0):
            raise ValueError('已删除记录顺序无效')
        positions = item.get('entry_positions')
        if positions is not None and (not isinstance(positions, list) or len(positions) != len(entries) or
                                      any(type(p) is not int or p < 0 for p in positions)):
            raise ValueError('已删除申报顺序无效')
        if item['kind'] == 'entries' and entries:
            raise ValueError('单条申报不能包含其他申报')
        key = {'projects': 'project_id', 'people': 'person_id'}.get(item['kind'])
        if key and any(e.get(key) != record['id'] for e in entries):
            raise ValueError('已删除申报关联错误')
        if not all(isinstance(item.get(k), str) and item[k].strip() for k in ('actor', 'at')):
            raise ValueError('已删除记录缺少操作人或时间')


def remove_record(state, kind, record_id, actor):
    if kind not in KINDS or not isinstance(record_id, str):
        raise ValueError('请选择要删除的项目、人员或申报')
    record = next((row for row in state[kind] if row['id'] == record_id), None)
    if record is None:
        raise ValueError('记录已不存在，请刷新台账')
    next_state = deepcopy(state)
    key = {'projects': 'project_id', 'people': 'person_id'}.get(kind)
    entries = [e for e in next_state['entries'] if key and e[key] == record_id]
    removed_ids = {e['id'] for e in entries}
    next_state[kind] = [row for row in next_state[kind] if row['id'] != record_id]
    if kind != 'entries':
        next_state['entries'] = [e for e in next_state['entries'] if e['id'] not in removed_ids]
    item = dict(id=str(uuid4()), kind=kind, record=deepcopy(record), entries=entries,
                position=next(i for i, row in enumerate(state[kind]) if row['id'] == record_id),
                entry_positions=[i for i, e in enumerate(state['entries']) if e['id'] in removed_ids],
                actor=actor, at=datetime.now(timezone.utc).isoformat())
    next_state.setdefault('deleted_records', []).insert(0, item)
    return next_state, item


def restore_record(state, deleted_id):
    item = next((row for row in state.get('deleted_records', []) if row['id'] == deleted_id), None)
    if item is None:
        raise ValueError('找不到已删除记录，可能已恢复，请刷新台账')
    kind, record = item['kind'], item['record']
    next_state = deepcopy(state)
    if any(row['id'] == record['id'] for row in state[kind]):
        raise ValueError('无法恢复：当前台账中已有相同编号的记录')
    next_state[kind].insert(min(item.get('position', len(next_state[kind])), len(next_state[kind])), deepcopy(record))
    if kind != 'entries':
        existing = {e['id'] for e in state['entries']}
        if any(e['id'] in existing for e in item['entries']):
            raise ValueError('无法恢复：当前台账中已有相同编号的申报')
        positions = item.get('entry_positions')
        if positions is None:
            next_state['entries'].extend(deepcopy(item['entries']))
        else:
            for position, entry in sorted(zip(positions, item['entries']), key=lambda pair: pair[0]):
                next_state['entries'].insert(min(position, len(next_state['entries'])), deepcopy(entry))
    projects = {p['id'] for p in next_state['projects']}
    people = {p['id'] for p in next_state['people']}
    if any(e['project_id'] not in projects for e in next_state['entries']):
        raise ValueError('请先恢复关联项目，再恢复此记录')
    if any(e['person_id'] not in people for e in next_state['entries']):
        raise ValueError('请先恢复关联人员，再恢复此记录')
    next_state['deleted_records'] = [row for row in next_state['deleted_records'] if row['id'] != deleted_id]
    return next_state, item


def certificate_ids(state):
    people = state['people'] + [item['record'] for item in state.get('deleted_records', []) if item['kind'] == 'people']
    return {p['certificate_id'] for p in people if p.get('certificate_id')}
