"""
Agnes AI Studio - Flask 应用工厂
"""

import os
import json
from flask import Flask, request
from flask_cors import CORS
from .config import get_base_path, ensure_output_dirs


def _brief(value, max_len=120):
    """截断超长值（如 base64 图片），日志只保留可读部分"""
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return s if len(s) <= max_len else s[:max_len] + f'...(共{len(s)}字符)'


def create_app():
    """创建并配置 Flask 应用"""
    # 前端构建产物目录
    frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'dist')
    has_frontend = os.path.exists(os.path.join(frontend_dist, 'index.html'))
    static_dir = frontend_dist if has_frontend else os.path.join(get_base_path(), 'static')

    app = Flask(
        __name__,
        static_folder=static_dir,
        static_url_path=''
    )
    CORS(app)

    # 确保输出目录存在
    ensure_output_dirs()

    # 注册 Blueprint
    from .routes.pages import pages_bp
    from .routes.api_config import config_bp
    from .routes.image import image_bp
    from .routes.video import video_bp
    from .routes.drama import drama_bp
    from .routes.drama_flow import flow_bp
    from .routes.files import files_bp
    from .routes.anchor import anchor_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(image_bp)
    app.register_blueprint(video_bp)
    app.register_blueprint(drama_bp)
    app.register_blueprint(flow_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(anchor_bp)

    @app.before_request
    def log_request_params():
        """打印所有写接口的入参，base64 等超长值自动截断"""
        if request.method in ('POST', 'PUT', 'PATCH'):
            data = request.get_json(silent=True) or {}
            brief_body = {k: _brief(v) for k, v in data.items()}
            files = list(request.files.keys())
            print(f"[REQ] {request.method} {request.path} body={brief_body}" + (f" files={files}" if files else ''), flush=True)

    return app
