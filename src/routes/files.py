"""
文件列表 + 关闭服务路由
"""

import os
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify

from ..config import get_app_dir, shutdown_event

files_bp = Blueprint('files', __name__)


@files_bp.route('/api/shutdown', methods=['POST'])
def api_shutdown():
    """关闭服务：通知所有后台线程退出，然后停止 Flask"""
    print("[关闭] 收到关闭请求，正在停止服务...")
    shutdown_event.set()
    threading.Timer(0.5, _do_shutdown).start()
    return jsonify({'success': True, 'message': '服务正在关闭'})


def _do_shutdown():
    """实际执行关闭"""
    try:
        func = request.environ.get('werkzeug.server.shutdown')
        if func:
            func()
    except Exception:
        pass
    os._exit(0)


@files_bp.route('/api/files/<subdir>', methods=['GET'])
def list_files(subdir):
    """列出本地已生成的文件。
    默认只返回顶层目录（首页用）；?scope=all 时额外纳入各短剧 dramas/<id>/videos|images
    （文件页用）。首页不传 scope，避免被大量短剧图挤出。"""
    if subdir not in ('videos', 'pictures'):
        return jsonify({'success': False, 'error': '无效目录'}), 400

    app_dir = get_app_dir()
    files = []
    # (磁盘目录, URL 前缀)
    roots = [(os.path.join(app_dir, subdir), f'/{subdir}/')]
    if request.args.get('scope') == 'all':
        drama_sub = 'videos' if subdir == 'videos' else 'images'
        dramas_dir = os.path.join(app_dir, 'dramas')
        if os.path.isdir(dramas_dir):
            for did in sorted(os.listdir(dramas_dir), reverse=True):
                roots.append((os.path.join(dramas_dir, did, drama_sub), f'/dramas/{did}/{drama_sub}/'))

    for target_dir, url_prefix in roots:
        if not os.path.isdir(target_dir):
            continue
        for f in os.listdir(target_dir):
            filepath = os.path.join(target_dir, f)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                files.append({
                    'filename': f,
                    'url': url_prefix + f,
                    'size': stat.st_size,
                    'size_display': _format_size(stat.st_size),
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })

    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify({'success': True, 'files': files})


def _format_size(size_bytes):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
