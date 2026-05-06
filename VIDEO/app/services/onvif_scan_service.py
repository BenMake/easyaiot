"""
ONVIF 分布式网段扫描：快速端口探测 → WS-Discovery / HTTP 探测 → 密码库撞库 → 自动注册
@author 翱翔的雄库鲁
@email andywebjava@163.com
@wechat EasyAIoT2025
"""
from __future__ import annotations

import concurrent.futures
import ipaddress
import json
import logging
import re
import socket
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_

from app.services.camera_service import (
    probe_onvif_http_endpoint,
    register_camera_by_onvif_with_credentials,
)
from models import Device, OnvifPasswordLibrary, OnvifScanIpBlacklist, OnvifScanSkipEntry, OnvifScanTask, db

logger = logging.getLogger(__name__)

WS_DISCOVERY_PORT = 3702

def normalize_scan_ip(ip: str) -> str:
    return (ip or '').strip()


def is_ip_blacklisted(ip: str) -> bool:
    """全局黑名单：该 IP 不参与扫描探测与 ONVIF 注册/更新。"""
    nip = normalize_scan_ip(ip)
    if not nip:
        return False
    return OnvifScanIpBlacklist.query.filter_by(ip=nip).first() is not None


def load_blacklist_normalized_set() -> set[str]:
    return {normalize_scan_ip(r.ip) for r in OnvifScanIpBlacklist.query.with_entities(OnvifScanIpBlacklist.ip).all()}


DEFAULT_CREDENTIALS = [
    {'username': 'admin', 'password': ''},
    {'username': 'admin', 'password': 'admin'},
    {'username': 'admin', 'password': '12345'},
    {'username': 'Administrator', 'password': ''},
    {'username': 'root', 'password': ''},
]


def _build_probe_xml() -> bytes:
    mid = f'uuid:{uuid.uuid4()}'
    body = f'''<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
  <s:Header>
    <a:Action s:mustUnderstand="1">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action>
    <a:MessageID>{mid}</a:MessageID>
    <a:To s:mustUnderstand="1">urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To>
  </s:Header>
  <s:Body>
    <d:Probe>
      <d:Types xmlns:dn="http://www.onvif.org/ver10/network/wsdl">dn:NetworkVideoTransmitter</d:Types>
    </d:Probe>
  </s:Body>
</s:Envelope>'''
    return body.encode('utf-8')


def ws_discovery_unicast_probe(ip: str, timeout_sec: float) -> list[str]:
    """向目标 IPv4 发送 WS-Discovery Probe（UDP 3702），返回 XAddr 列表。"""
    xaddrs: list[str] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout_sec)
    try:
        sock.sendto(_build_probe_xml(), (ip, WS_DISCOVERY_PORT))
        while True:
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            text = data.decode('utf-8', errors='ignore')
            for m in re.finditer(r'<[^>]*XAddrs[^>]*>([^<]+)</', text, re.I):
                raw = m.group(1).strip()
                for part in re.split(r'\s+', raw):
                    p = part.strip()
                    if p.startswith('http://') or p.startswith('https://'):
                        xaddrs.append(p)
    except OSError as e:
        logger.debug('WS-Discovery UDP %s: %s', ip, e)
    finally:
        sock.close()
    return list(dict.fromkeys(xaddrs))


def _parse_host_port_from_xaddr(url: str) -> Optional[tuple[str, int]]:
    m = re.match(r'https?://([^/:]+)(?::(\d+))?(?:/|$)', url, re.I)
    if not m:
        return None
    host = m.group(1)
    port = int(m.group(2) or (443 if url.lower().startswith('https') else 80))
    return host, port


def pick_onvif_http_port(
    ip: str,
    open_quick_ports: list[int],
    xaddrs: list[str],
    http_timeout: float,
) -> Optional[int]:
    """从 WS-Discovery 的 XAddr 或已开放端口中确定可用的 ONVIF HTTP 服务端口。"""
    for xa in xaddrs:
        hp = _parse_host_port_from_xaddr(xa)
        if not hp:
            continue
        host, port = hp
        if host != ip and host.replace('[', '').replace(']', '') != ip:
            continue
        if probe_onvif_http_endpoint(ip, port, http_timeout):
            return port
    for port in open_quick_ports:
        if port in (80, 8000, 8080, 8899, 8888, 7080):
            if probe_onvif_http_endpoint(ip, port, http_timeout):
                return port
    return None


def _tcp_quick_open(ip: str, port: int, timeout_sec: float) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout_sec)
    try:
        return s.connect_ex((ip, port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def quick_scan_ports(ip: str, ports: list[int], timeout_ms: int) -> list[int]:
    t = max(timeout_ms, 10) / 1000.0
    open_ports: list[int] = []
    for p in ports:
        if _tcp_quick_open(ip, p, t):
            open_ports.append(p)
    return open_ports


def build_ipv4_list(cidrs: list[str], max_hosts: int) -> list[str]:
    ips: list[str] = []
    for cidr in cidrs:
        cidr = (cidr or '').strip()
        if not cidr:
            continue
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if not isinstance(net, ipaddress.IPv4Network):
            continue
        for h in net.hosts():
            ips.append(str(h))
            if len(ips) >= max_hosts:
                return ips
    return ips


def next_ip_batch(ips: list[str], cursor: int, batch: int) -> tuple[list[str], int]:
    if not ips:
        return [], 0
    n = len(ips)
    m = min(batch, n)
    out = [ips[(cursor + i) % n] for i in range(m)]
    return out, (cursor + m) % n


def skip_key_for_ip(task_id: int, ip: str) -> str:
    return f'{task_id}:{ip}:port_open_no_onvif'


def is_ip_skipped(task_id: int, ip: str) -> bool:
    key = skip_key_for_ip(task_id, ip)
    row = OnvifScanSkipEntry.query.filter_by(skip_key=key, released=False).first()
    return row is not None


def record_skip_port_open_no_onvif(task_id: int, ip: str, open_ports: list[int], note: str = '') -> None:
    key = skip_key_for_ip(task_id, ip)
    existing = OnvifScanSkipEntry.query.filter_by(skip_key=key).first()
    ports_s = ','.join(str(p) for p in sorted(set(open_ports)))
    if existing:
        if not existing.released:
            return
        existing.released = False
        existing.open_ports = ports_s
        existing.reason = 'port_open_no_onvif'
        existing.note = note[:500] if note else None
        db.session.commit()
        return
    db.session.add(
        OnvifScanSkipEntry(
            task_id=task_id,
            skip_key=key,
            ip=ip,
            open_ports=ports_s,
            reason='port_open_no_onvif',
            released=False,
            note=note[:500] if note else None,
        )
    )
    db.session.commit()


def release_skip_entry(entry_id: int) -> None:
    row = OnvifScanSkipEntry.query.get(entry_id)
    if not row:
        raise ValueError('跳过记录不存在')
    row.released = True
    db.session.commit()


def list_ip_blacklist(page_no: int, page_size: int) -> dict[str, Any]:
    q = OnvifScanIpBlacklist.query.order_by(OnvifScanIpBlacklist.id.desc())
    total = q.count()
    rows = q.offset((page_no - 1) * page_size).limit(page_size).all()
    return {'total': total, 'items': [x.to_dict() for x in rows]}


def add_ip_blacklist_batch(ips: list[str], note: str = '') -> dict[str, Any]:
    added = 0
    skipped = 0
    note_s = (note or '')[:500] or None
    for raw in ips:
        nip = normalize_scan_ip(raw)
        if not nip:
            continue
        try:
            ipaddress.ip_address(nip)
        except ValueError:
            skipped += 1
            continue
        if OnvifScanIpBlacklist.query.filter_by(ip=nip).first():
            skipped += 1
            continue
        db.session.add(OnvifScanIpBlacklist(ip=nip, note=note_s))
        added += 1
    db.session.commit()
    return {'added': added, 'skipped': skipped}


def remove_ip_blacklist(entry_id: int) -> None:
    row = OnvifScanIpBlacklist.query.get(entry_id)
    if not row:
        raise ValueError('黑名单记录不存在')
    db.session.delete(row)
    db.session.commit()


def list_server_candidates(page_no: int, page_size: int) -> dict[str, Any]:
    """库中设备 IP 去重列表；已在黑名单中的 IP 不出现。"""
    bl_ips = list({normalize_scan_ip(r.ip) for r in OnvifScanIpBlacklist.query.with_entities(OnvifScanIpBlacklist.ip).all()})
    q = db.session.query(
        Device.ip,
        func.count(Device.id).label('device_count'),
        func.max(Device.name).label('sample_name'),
    ).filter(
        Device.ip.isnot(None),
        Device.ip != '',
        func.trim(Device.ip) != '',
    )
    if bl_ips:
        q = q.filter(~Device.ip.in_(bl_ips))
    rows = q.group_by(Device.ip).order_by(Device.ip).all()
    total = len(rows)
    start = (page_no - 1) * page_size
    chunk = rows[start : start + page_size]
    items = [
        {'ip': r[0], 'device_count': int(r[1]), 'sample_name': r[2] or ''}
        for r in chunk
    ]
    return {'total': total, 'items': items}


def list_password_libraries(page_no: int, page_size: int) -> dict[str, Any]:
    q = OnvifPasswordLibrary.query.order_by(OnvifPasswordLibrary.id.desc())
    total = q.count()
    items = q.offset((page_no - 1) * page_size).limit(page_size).all()
    return {'total': total, 'items': [x.to_dict() for x in items]}


def get_password_library(lib_id: int, with_secrets: bool = False):
    row = OnvifPasswordLibrary.query.get(lib_id)
    if not row:
        raise ValueError('密码库不存在')
    return row.to_dict_with_secrets() if with_secrets else row.to_dict()


def create_password_library(name: str, lib_code: str, credentials: list[dict], description: str = '') -> int:
    if not name or not name.strip():
        raise ValueError('名称不能为空')
    if not lib_code or not lib_code.strip():
        raise ValueError('lib_code 不能为空')
    if OnvifPasswordLibrary.query.filter_by(lib_code=lib_code.strip()).first():
        raise ValueError('lib_code 已存在')
    row = OnvifPasswordLibrary(
        name=name.strip(),
        lib_code=lib_code.strip(),
        description=(description or '')[:500] or None,
        credentials_json=json.dumps(credentials or [], ensure_ascii=False),
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def update_password_library(lib_id: int, data: dict) -> None:
    row = OnvifPasswordLibrary.query.get(lib_id)
    if not row:
        raise ValueError('密码库不存在')
    if 'name' in data and data['name']:
        row.name = str(data['name']).strip()
    if 'description' in data:
        row.description = (data.get('description') or '')[:500] or None
    if 'credentials' in data:
        row.credentials_json = json.dumps(data['credentials'] or [], ensure_ascii=False)
    db.session.commit()


def delete_password_library(lib_id: int) -> None:
    row = OnvifPasswordLibrary.query.get(lib_id)
    if not row:
        raise ValueError('密码库不存在')
    if OnvifScanTask.query.filter_by(password_library_id=lib_id).first():
        raise ValueError('仍有扫描任务关联该密码库，无法删除')
    db.session.delete(row)
    db.session.commit()


def list_scan_tasks(page_no: int, page_size: int) -> dict[str, Any]:
    q = OnvifScanTask.query.order_by(OnvifScanTask.id.desc())
    total = q.count()
    items = q.offset((page_no - 1) * page_size).limit(page_size).all()
    return {'total': total, 'items': [x.to_dict() for x in items]}


def get_scan_task(task_id: int) -> dict:
    row = OnvifScanTask.query.get(task_id)
    if not row:
        raise ValueError('任务不存在')
    return row.to_dict()


def create_scan_task(data: dict) -> int:
    name = (data.get('task_name') or '').strip()
    if not name:
        raise ValueError('task_name 不能为空')
    cidrs = data.get('cidrs') or []
    if not isinstance(cidrs, list) or not cidrs:
        raise ValueError('cidrs 必须为非空 JSON 数组')
    task_code = (data.get('task_code') or '').strip() or f'onvif-scan-{uuid.uuid4().hex[:16]}'
    if OnvifScanTask.query.filter_by(task_code=task_code).first():
        raise ValueError('task_code 已存在')

    ports = data.get('quick_scan_ports') or [80, 554]
    row = OnvifScanTask(
        task_code=task_code,
        task_name=name,
        cidrs_json=json.dumps(cidrs, ensure_ascii=False),
        password_library_id=data.get('password_library_id'),
        quick_scan_ports_json=json.dumps(ports, ensure_ascii=False),
        quick_scan_timeout_ms=int(data.get('quick_scan_timeout_ms', 200)),
        ws_discovery_timeout_ms=int(data.get('ws_discovery_timeout_ms', 800)),
        onvif_http_probe_timeout=float(data.get('onvif_http_probe_timeout', 0.4)),
        max_hosts_per_cycle=int(data.get('max_hosts_per_cycle', 1024)),
        max_total_hosts=int(data.get('max_total_hosts', 65536)),
        scan_interval_sec=int(data.get('scan_interval_sec', 120)),
        is_enabled=bool(data.get('is_enabled', False)),
        auto_register=bool(data.get('auto_register', True)),
        assigned_worker_id=(data.get('assigned_worker_id') or '').strip() or None,
        description=(data.get('description') or '')[:500] or None,
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def update_scan_task(task_id: int, data: dict) -> None:
    row = OnvifScanTask.query.get(task_id)
    if not row:
        raise ValueError('任务不存在')
    if 'task_name' in data and data['task_name']:
        row.task_name = str(data['task_name']).strip()
    if 'cidrs' in data:
        if not isinstance(data['cidrs'], list) or not data['cidrs']:
            raise ValueError('cidrs 必须为非空数组')
        row.cidrs_json = json.dumps(data['cidrs'], ensure_ascii=False)
        row.scan_cursor = 0
    if 'password_library_id' in data:
        v = data['password_library_id']
        row.password_library_id = int(v) if v is not None else None
    if 'quick_scan_ports' in data:
        row.quick_scan_ports_json = json.dumps(data['quick_scan_ports'], ensure_ascii=False)
    if 'quick_scan_timeout_ms' in data:
        row.quick_scan_timeout_ms = int(data['quick_scan_timeout_ms'])
    if 'ws_discovery_timeout_ms' in data:
        row.ws_discovery_timeout_ms = int(data['ws_discovery_timeout_ms'])
    if 'onvif_http_probe_timeout' in data:
        row.onvif_http_probe_timeout = float(data['onvif_http_probe_timeout'])
    if 'max_hosts_per_cycle' in data:
        row.max_hosts_per_cycle = int(data['max_hosts_per_cycle'])
    if 'max_total_hosts' in data:
        row.max_total_hosts = int(data['max_total_hosts'])
    if 'scan_interval_sec' in data:
        row.scan_interval_sec = int(data['scan_interval_sec'])
    if 'is_enabled' in data:
        row.is_enabled = bool(data['is_enabled'])
    if 'auto_register' in data:
        row.auto_register = bool(data['auto_register'])
    if 'assigned_worker_id' in data:
        row.assigned_worker_id = (data.get('assigned_worker_id') or '').strip() or None
    if 'description' in data:
        row.description = (data.get('description') or '')[:500] or None
    db.session.commit()


def delete_scan_task(task_id: int) -> None:
    row = OnvifScanTask.query.get(task_id)
    if not row:
        raise ValueError('任务不存在')
    db.session.delete(row)
    db.session.commit()


def list_skip_entries(task_id: int, page_no: int, page_size: int, include_released: bool = False) -> dict[str, Any]:
    q = OnvifScanSkipEntry.query.filter_by(task_id=task_id)
    if not include_released:
        q = q.filter_by(released=False)
    q = q.order_by(OnvifScanSkipEntry.id.desc())
    total = q.count()
    items = q.offset((page_no - 1) * page_size).limit(page_size).all()
    return {'total': total, 'items': [x.to_dict() for x in items]}


def _credentials_for_task(task: OnvifScanTask) -> list[dict]:
    if task.password_library_id:
        lib = OnvifPasswordLibrary.query.get(task.password_library_id)
        if lib:
            creds = lib._parse_credentials()
            if creds:
                return creds
    return list(DEFAULT_CREDENTIALS)


def try_claim_task(task_id: int, worker_id: str, lease_sec: int = 90) -> bool:
    now = datetime.utcnow()
    until = now + timedelta(seconds=lease_sec)
    row = OnvifScanTask.query.get(task_id)
    if not row or not row.is_enabled:
        return False
    if row.assigned_worker_id and row.assigned_worker_id != worker_id:
        return False
    if row.claim_worker_id and row.claim_worker_id != worker_id:
        if row.claim_lease_until and row.claim_lease_until > now:
            return False
    row.claim_worker_id = worker_id
    row.claim_lease_until = until
    db.session.commit()
    return True


def renew_task_claim(task_id: int, worker_id: str, lease_sec: int = 90) -> None:
    row = OnvifScanTask.query.get(task_id)
    if not row or row.claim_worker_id != worker_id:
        return
    row.claim_lease_until = datetime.utcnow() + timedelta(seconds=lease_sec)
    db.session.commit()


def release_task_claim(task_id: int, worker_id: str) -> None:
    row = OnvifScanTask.query.get(task_id)
    if not row or row.claim_worker_id != worker_id:
        return
    row.claim_worker_id = None
    row.claim_lease_until = None
    db.session.commit()


def pick_tasks_for_worker(worker_id: str) -> list[OnvifScanTask]:
    now = datetime.utcnow()
    q = OnvifScanTask.query.filter(
        OnvifScanTask.is_enabled == True,  # noqa: E712
        or_(
            OnvifScanTask.assigned_worker_id.is_(None),
            OnvifScanTask.assigned_worker_id == '',
            OnvifScanTask.assigned_worker_id == worker_id,
        ),
        or_(
            OnvifScanTask.claim_worker_id.is_(None),
            OnvifScanTask.claim_worker_id == worker_id,
            OnvifScanTask.claim_lease_until.is_(None),
            OnvifScanTask.claim_lease_until < now,
        ),
    )
    return q.all()


def run_scan_cycle(task_id: int, worker_id: str) -> dict[str, Any]:
    """执行一轮：快速端口（多线程）→ 主线程内 WS-Discovery / HTTP 探测与撞库（避免跨线程用同一 DB 会话）。"""
    renew_task_claim(task_id, worker_id, lease_sec=120)
    task = OnvifScanTask.query.get(task_id)
    if not task:
        return {'error': 'task_not_found'}

    cidrs = json.loads(task.cidrs_json or '[]')
    ports = json.loads(task.quick_scan_ports_json or '[80,554]')
    ips = build_ipv4_list(cidrs, task.max_total_hosts)
    if not ips:
        task.last_error = '无有效 IPv4 网段'
        task.last_cycle_at = datetime.utcnow()
        db.session.commit()
        return {'error': 'no_ips'}

    batch, new_cursor = next_ip_batch(ips, task.scan_cursor, task.max_hosts_per_cycle)
    task.scan_cursor = new_cursor

    bl_set = load_blacklist_normalized_set()
    batch_eff = [ip for ip in batch if normalize_scan_ip(ip) not in bl_set]

    stats: dict[str, Any] = {
        'batch_ips': len(batch),
        'blacklist_skipped': len(batch) - len(batch_eff),
        'alive': 0,
        'ws_discovery_hits': 0,
        'onvif_http_hits': 0,
        'auth_ok': 0,
        'registered': 0,
        'updated': 0,
        'skipped_known_dead': 0,
        'new_skip_entries': 0,
    }

    http_to = task.onvif_http_probe_timeout
    ws_to = min(task.ws_discovery_timeout_ms / 1000.0, 3.0)
    quick_ms = task.quick_scan_timeout_ms

    ip_open: dict[str, list[int]] = {}
    if not batch_eff:
        task.last_stats_json = json.dumps(stats, ensure_ascii=False)
        task.last_cycle_at = datetime.utcnow()
        task.last_error = None
        db.session.commit()
        return stats

    workers = min(256, max(32, len(batch_eff)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        fut_map = {ex.submit(quick_scan_ports, ip, ports, quick_ms): ip for ip in batch_eff}
        for fut in concurrent.futures.as_completed(fut_map):
            ip = fut_map[fut]
            try:
                ip_open[ip] = fut.result()
            except Exception as e:
                logger.debug('quick scan %s: %s', ip, e)
                ip_open[ip] = []

    creds = _credentials_for_task(task)

    for ip, open_p in ip_open.items():
        if not open_p:
            continue
        if is_ip_skipped(task.id, ip):
            stats['skipped_known_dead'] += 1
            continue
        stats['alive'] += 1

        xaddrs = ws_discovery_unicast_probe(ip, ws_to)
        if xaddrs:
            stats['ws_discovery_hits'] += 1

        onvif_port = pick_onvif_http_port(ip, open_p, xaddrs, http_to)
        if not onvif_port:
            record_skip_port_open_no_onvif(task.id, ip, open_p, 'alive_but_no_onvif')
            stats['new_skip_entries'] += 1
            continue

        stats['onvif_http_hits'] += 1
        authed = False
        if task.auto_register:
            for c in creds:
                u, p = c.get('username', ''), c.get('password', '')
                try:
                    _did, outcome = register_camera_by_onvif_with_credentials(ip, onvif_port, u, p)
                    authed = True
                    if outcome == 'updated':
                        stats['updated'] += 1
                    elif outcome == 'created':
                        stats['registered'] += 1
                    elif outcome == 'blacklisted_skip':
                        stats['blacklist_skipped'] += 1
                    break
                except Exception:
                    continue
        else:
            from app.services.camera_service import _create_onvif_camera

            for c in creds:
                u, p = c.get('username', ''), c.get('password', '')
                try:
                    _create_onvif_camera('temp_onvif_scan', ip, onvif_port, u, p)
                    authed = True
                    break
                except Exception:
                    continue

        if authed:
            stats['auth_ok'] += 1

    task.last_stats_json = json.dumps(stats, ensure_ascii=False)
    task.last_cycle_at = datetime.utcnow()
    task.last_error = None
    db.session.commit()
    return stats


def run_worker_tick(worker_id: str) -> dict[str, Any] | None:
    """供独立进程调用：抢占一个任务并执行一轮扫描。"""
    tasks = pick_tasks_for_worker(worker_id)
    for t in tasks:
        if try_claim_task(t.id, worker_id, lease_sec=120):
            stats = run_scan_cycle(t.id, worker_id)
            return {'task_id': t.id, 'task_code': t.task_code, 'stats': stats}
    return None
