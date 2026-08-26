"""
Agnes AI Studio - Flask 应用工厂
"""

import os
from flask import Flask
from flask_cors import CORS
from .config import get_base_path, ensure_output_dirs


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
    from .routes.files import files_bp
    from .routes.anchor import anchor_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(image_bp)
    app.register_blueprint(video_bp)
    app.register_blueprint(drama_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(anchor_bp)

    return app
