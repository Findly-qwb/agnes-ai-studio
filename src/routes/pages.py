"""
首页路由 + 静态文件服务 + React SPA 兜底
"""

import os
from flask import Blueprint, send_from_directory
from ..config import get_base_path, get_app_dir, ensure_output_dirs

pages_bp = Blueprint('pages', __name__)

FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'frontend', 'dist')


def _static_dir():
    if os.path.exists(os.path.join(FRONTEND_DIST, 'index.html')):
        return FRONTEND_DIST
    return os.path.join(get_base_path(), 'static')


@pages_bp.route('/')
def index():
    return send_from_directory(_static_dir(), 'index.html')


@pages_bp.route('/assets/<path:filename>')
def serve_assets(filename):
    """React 构建产物的静态资源"""
    return send_from_directory(os.path.join(_static_dir(), 'assets'), filename)


@pages_bp.route('/videos/<path:filename>')
def serve_video(filename):
    videos_dir, _ = ensure_output_dirs()
    return send_from_directory(videos_dir, filename)


@pages_bp.route('/pictures/<path:filename>')
def serve_picture(filename):
    _, pictures_dir = ensure_output_dirs()
    return send_from_directory(pictures_dir, filename)


@pages_bp.route('/dramas/<path:filename>')
def serve_drama_file(filename):
    """服务短剧输出文件（图片/视频）"""
    app_dir = get_app_dir()
    dramas_dir = os.path.join(app_dir, 'dramas')
    os.makedirs(dramas_dir, exist_ok=True)
    return send_from_directory(dramas_dir, filename)


@pages_bp.route('/anchor/<path:filename>')
def serve_anchor_file(filename):
    """服务数字人口播输出文件（形象图/视频/音频）"""
    app_dir = get_app_dir()
    anchor_dir = os.path.join(app_dir, 'anchor')
    os.makedirs(anchor_dir, exist_ok=True)
    return send_from_directory(anchor_dir, filename)
