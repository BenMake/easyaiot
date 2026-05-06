#!/usr/bin/env python3
"""
ONVIF 分布式扫描注册 Worker：从数据库抢占已启用的扫描任务，按网段轮询执行
多机部署：每台机器运行本进程，配置相同 DATABASE_URL 与唯一 ONVIF_SCANNER_WORKER_ID。

@author 翱翔的雄库鲁
@email andywebjava@163.com
@wechat EasyAIoT2025
"""
import logging
import os
import socket
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

video_root = str(Path(__file__).resolve().parents[2])
if video_root not in sys.path:
    sys.path.insert(0, video_root)

load_dotenv(os.path.join(video_root, '.env'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('onvif_scanner')

_flask_app = None


def get_flask_app():
    global _flask_app
    if _flask_app is None:
        from flask import Flask
        from models import db

        app = Flask(__name__)
        database_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/iot_video')
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 3600,
            'pool_size': 5,
            'max_overflow': 10,
            'connect_args': {'connect_timeout': 10},
        }
        db.init_app(app)
        _flask_app = app
    return _flask_app


def main():
    worker_id = (os.getenv('ONVIF_SCANNER_WORKER_ID') or '').strip()
    if not worker_id:
        worker_id = f'{socket.gethostname()}-{os.getpid()}'
    idle_sec = int(os.getenv('ONVIF_SCANNER_IDLE_SEC', '10'))
    active_pause = float(os.getenv('ONVIF_SCANNER_ACTIVE_PAUSE_SEC', '1.5'))

    logger.info('ONVIF scanner worker 启动 worker_id=%s', worker_id)
    app = get_flask_app()

    from app.services.onvif_scan_service import run_worker_tick
    from models import OnvifScanTask

    while True:
        try:
            with app.app_context():
                r = run_worker_tick(worker_id)
            if r:
                logger.info('扫描完成 task_id=%s stats=%s', r.get('task_id'), r.get('stats'))
                with app.app_context():
                    t = OnvifScanTask.query.get(r.get('task_id'))
                    interval = int(t.scan_interval_sec) if t else 120
                interval = max(5, min(interval, 86400))
                time.sleep(max(active_pause, float(interval)))
            else:
                time.sleep(idle_sec)
        except KeyboardInterrupt:
            logger.info('退出')
            break
        except Exception as e:
            logger.exception('扫描循环异常: %s', e)
            time.sleep(idle_sec)


if __name__ == '__main__':
    main()
