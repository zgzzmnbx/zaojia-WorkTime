"""Background calendar mirroring from the user-configured intranet service."""
from datetime import datetime, timedelta, timezone
from calendar_io import fetch_intranet_calendar


def sync_calendar(store, conflict_type, now=None, fetch=fetch_intranet_calendar):
    now = now or datetime.now(timezone.utc)
    revision, state = store.read()
    settings = state.get('calendar_update', {})
    if settings.get('automatic') is not True or not settings.get('url'):
        return
    url = settings['url']
    status = store.calendar_status()
    if status.get('url') == url and status.get('checked_at'):
        try:
            checked = datetime.fromisoformat(status['checked_at'])
            delay = timedelta(hours=1) if status.get('error') else timedelta(days=7)
            if now < checked + delay:
                return
        except (ValueError, TypeError):
            pass
    status = {'url': url, 'checked_at': now.isoformat()}
    try:
        package = fetch(url)
        # Network access occurs outside the DB transaction. Re-read afterwards
        # so a changed source, disabled schedule, or concurrent edit wins.
        revision, current = store.read()
        if current.get('calendar_update', {}) != settings:
            return
        incoming = {c['year']: c for c in package['calendars']}
        old = {c['year']: c for c in current['calendars']}
        changed = [year for year, value in incoming.items() if old.get(year) != value]
        if changed:
            current['calendars'] = sorted({**old, **incoming}.values(), key=lambda c: c['year'])
            store.save(current, revision, '系统（日历自动同步）',
                       '内网日历自动更新：' + '、'.join(map(str, sorted(changed))))
        status.update(error='', changed_years=sorted(changed), version=package.get('bundle_version', ''))
    except conflict_type:
        status['error'] = '台账同时被修改，稍后重试'
    except (ValueError, OSError) as exc:
        status['error'] = str(exc)
    store.save_calendar_status(status)


def calendar_sync_loop(stores, conflict_type, stop):
    while not stop.is_set():
        for store in stores.values():
            try:
                sync_calendar(store, conflict_type)
            except Exception:
                # Report unexpected worker failures without terminating serving.
                import traceback
                traceback.print_exc()
        stop.wait(60)
