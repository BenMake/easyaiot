"""
ONVIF 分布式扫描任务与密码库 API
@author 翱翔的雄库鲁
@email andywebjava@163.com
@wechat EasyAIoT2025
"""
import logging
import os

from flask import Blueprint, jsonify, request

from app.services import onvif_scan_service as svc

onvif_scan_bp = Blueprint('onvif_scan', __name__)
logger = logging.getLogger(__name__)


def _ok(data=None, msg='success'):
    return jsonify({'code': 0, 'msg': msg, 'data': data})


def _err(code, msg, http=400):
    return jsonify({'code': code, 'msg': msg}), http


@onvif_scan_bp.route('/password-library/list', methods=['GET'])
def password_library_list():
    try:
        page_no = int(request.args.get('pageNo', 1))
        page_size = int(request.args.get('pageSize', 20))
        r = svc.list_password_libraries(page_no, page_size)
        return jsonify({'code': 0, 'msg': 'success', 'data': r['items'], 'total': r['total']})
    except Exception as e:
        logger.error('password_library_list: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/password-library/<int:lib_id>', methods=['GET'])
def password_library_get(lib_id):
    try:
        with_secrets = request.args.get('with_secrets', '0') == '1'
        return _ok(svc.get_password_library(lib_id, with_secrets=with_secrets))
    except ValueError as e:
        return _err(400, str(e))
    except Exception as e:
        logger.error('password_library_get: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/password-library', methods=['POST'])
def password_library_create():
    try:
        data = request.get_json() or {}
        name = data.get('name')
        lib_code = data.get('lib_code')
        creds = data.get('credentials') or []
        if not isinstance(creds, list):
            return _err(400, 'credentials 须为数组')
        lid = svc.create_password_library(name, lib_code, creds, data.get('description', ''))
        return _ok({'id': lid})
    except ValueError as e:
        return _err(400, str(e))
    except Exception as e:
        logger.error('password_library_create: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/password-library/<int:lib_id>', methods=['PUT'])
def password_library_update(lib_id):
    try:
        svc.update_password_library(lib_id, request.get_json() or {})
        return _ok()
    except ValueError as e:
        return _err(400, str(e))
    except Exception as e:
        logger.error('password_library_update: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/password-library/<int:lib_id>', methods=['DELETE'])
def password_library_delete(lib_id):
    try:
        svc.delete_password_library(lib_id)
        return _ok()
    except ValueError as e:
        return _err(400, str(e))
    except Exception as e:
        logger.error('password_library_delete: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/task/list', methods=['GET'])
def task_list():
    try:
        page_no = int(request.args.get('pageNo', 1))
        page_size = int(request.args.get('pageSize', 20))
        r = svc.list_scan_tasks(page_no, page_size)
        return jsonify({'code': 0, 'msg': 'success', 'data': r['items'], 'total': r['total']})
    except Exception as e:
        logger.error('task_list: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/task/<int:task_id>', methods=['GET'])
def task_get(task_id):
    try:
        return _ok(svc.get_scan_task(task_id))
    except ValueError as e:
        return _err(400, str(e))
    except Exception as e:
        logger.error('task_get: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/task', methods=['POST'])
def task_create():
    try:
        data = request.get_json() or {}
        tid = svc.create_scan_task(data)
        return _ok({'id': tid})
    except ValueError as e:
        return _err(400, str(e))
    except Exception as e:
        logger.error('task_create: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/task/<int:task_id>', methods=['PUT'])
def task_update(task_id):
    try:
        svc.update_scan_task(task_id, request.get_json() or {})
        return _ok()
    except ValueError as e:
        return _err(400, str(e))
    except Exception as e:
        logger.error('task_update: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/task/<int:task_id>', methods=['DELETE'])
def task_delete(task_id):
    try:
        svc.delete_scan_task(task_id)
        return _ok()
    except ValueError as e:
        return _err(400, str(e))
    except Exception as e:
        logger.error('task_delete: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/task/<int:task_id>/skip/list', methods=['GET'])
def skip_list(task_id):
    try:
        page_no = int(request.args.get('pageNo', 1))
        page_size = int(request.args.get('pageSize', 20))
        inc = request.args.get('include_released', '0') == '1'
        r = svc.list_skip_entries(task_id, page_no, page_size, include_released=inc)
        return jsonify({'code': 0, 'msg': 'success', 'data': r['items'], 'total': r['total']})
    except Exception as e:
        logger.error('skip_list: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/skip/<int:entry_id>/release', methods=['POST'])
def skip_release(entry_id):
    try:
        svc.release_skip_entry(entry_id)
        return _ok()
    except ValueError as e:
        return _err(400, str(e))
    except Exception as e:
        logger.error('skip_release: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/ip-blacklist/list', methods=['GET'])
def ip_blacklist_list():
    try:
        page_no = int(request.args.get('pageNo', 1))
        page_size = int(request.args.get('pageSize', 20))
        r = svc.list_ip_blacklist(page_no, page_size)
        return jsonify({'code': 0, 'msg': 'success', 'data': r['items'], 'total': r['total']})
    except Exception as e:
        logger.error('ip_blacklist_list: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/ip-blacklist/batch', methods=['POST'])
def ip_blacklist_batch():
    try:
        data = request.get_json() or {}
        ips = data.get('ips')
        if ips is None:
            raw = data.get('raw') or ''
            ips = [x.strip() for x in str(raw).replace(',', '\n').split('\n') if x.strip()]
        elif isinstance(ips, str):
            ips = [x.strip() for x in ips.replace(',', '\n').split('\n') if x.strip()]
        if not isinstance(ips, list):
            return _err(400, 'ips 须为数组或 raw 文本')
        note = data.get('note') or ''
        r = svc.add_ip_blacklist_batch(ips, note)
        return _ok(r)
    except Exception as e:
        logger.error('ip_blacklist_batch: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/ip-blacklist/<int:entry_id>', methods=['DELETE'])
def ip_blacklist_delete(entry_id):
    try:
        svc.remove_ip_blacklist(entry_id)
        return _ok()
    except ValueError as e:
        return _err(400, str(e))
    except Exception as e:
        logger.error('ip_blacklist_delete: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/server-candidates/list', methods=['GET'])
def server_candidates_list():
    try:
        page_no = int(request.args.get('pageNo', 1))
        page_size = int(request.args.get('pageSize', 20))
        r = svc.list_server_candidates(page_no, page_size)
        return jsonify({'code': 0, 'msg': 'success', 'data': r['items'], 'total': r['total']})
    except Exception as e:
        logger.error('server_candidates_list: %s', e, exc_info=True)
        return _err(500, str(e), 500)


@onvif_scan_bp.route('/worker/tick', methods=['POST'])
def worker_tick_once():
    """手动触发一轮分布式抢占扫描（便于联调；生产请用 onvif_scanner_service 常驻进程）。"""
    key = os.getenv('ONVIF_SCAN_INTERNAL_KEY', '').strip()
    if key:
        if request.headers.get('X-Internal-Key', '') != key:
            return _err(403, 'forbidden', 403)
    wid = (request.headers.get('X-Worker-Id') or os.getenv('ONVIF_SCANNER_WORKER_ID') or 'http-tick').strip()
    try:
        r = svc.run_worker_tick(wid)
        return _ok(r)
    except Exception as e:
        logger.error('worker_tick_once: %s', e, exc_info=True)
        return _err(500, str(e), 500)
