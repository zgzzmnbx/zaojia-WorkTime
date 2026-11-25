"""Offline calendar packages, validated before the normal revision-checked save."""
import json
import http.client
import ipaddress
import socket
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from engine import empty_state, validate


def calendar_package(package):
    if not isinstance(package, dict) or package.get('format') != 'expert-hours-calendars' or type(package.get('version')) is not int or package['version'] != 1:
        raise ValueError('请选择本工具的日历 JSON 数据包（格式版本 1）')
    calendars = package.get('calendars')
    if not isinstance(calendars, list) or not calendars or len(calendars) > 101:
        raise ValueError('日历包须包含 1～101 个年度')
    state = empty_state()
    state['calendars'] = calendars
    try:
        validate(state)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ValueError('日历包无效：' + str(exc))
    return {**package, 'calendars': sorted(calendars, key=lambda c: c['year'])}


def bundled_calendars():
    path = Path(__file__).resolve().parent / 'public' / 'work-calendars.json'
    return calendar_package(json.loads(path.read_text(encoding='utf-8')))


INTRANET_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8', 'fc00::/7', '::1/128',
))


def calendar_url(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ch.isspace() for ch in url):
        raise ValueError('请填写有效的内网日历服务地址')
    try:
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.fragment:
            raise ValueError()
    except ValueError:
        raise ValueError('日历地址须为内网 HTTP 或 HTTPS 地址，不能带账号密码或片段')
    return parsed, port


def fetch_intranet_calendar(url):
    """Read a bounded calendar response directly from a private network host."""
    parsed, port = calendar_url(url)
    try:
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except OSError:
        raise ValueError('无法解析内网日历服务器，请检查地址和内网连接')
    if not addresses:
        raise ValueError('内网日历服务器没有可用地址')
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not any(ip in network for network in INTRANET_NETWORKS):
            raise ValueError('日历更新仅支持内网地址，请填写单位内网日历服务')
    host_ip = addresses[0][4][0]
    connection_type = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, port, timeout=5)
    # Pin the checked address, retain the original Host and TLS certificate name,
    # and avoid environment proxy settings or redirect-based external requests.
    connection._create_connection = lambda address, timeout, source_address=None: socket.create_connection(
        (host_ip, port), timeout, source_address)
    try:
        target = parsed.path or '/'
        if parsed.query:
            target += '?' + parsed.query
        connection.request('GET', target, headers={'Accept': 'application/json', 'User-Agent': 'ExpertHours-Calendar/1'})
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise ValueError('日历地址发生跳转，请填写内网日历接口的最终地址')
        if response.status != 200:
            raise ValueError(f'内网日历服务返回 HTTP {response.status}')
        length = response.getheader('Content-Length')
        if length is not None and (not length.isdigit() or int(length) > 1000000):
            raise ValueError('内网日历数据超过 1 MB 或长度无效')
        raw = response.read(1000001)
        if len(raw) > 1000000:
            raise ValueError('内网日历数据超过 1 MB')
        package = calendar_package(json.loads(raw.decode('utf-8-sig')))
    except ssl.SSLError:
        raise ValueError('内网 HTTPS 证书校验失败，请核对服务证书与地址')
    except (OSError, http.client.HTTPException):
        raise ValueError('无法连接内网日历服务或连接超时，现有日历仍可使用')
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError('内网地址返回的不是有效的日历 JSON，请检查接口地址')
    finally:
        connection.close()
    return {**package, 'fetched_from': url, 'fetched_at': datetime.now(timezone.utc).isoformat()}
