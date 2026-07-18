"""
模型选项与任务状态模块
包含：模型选项字典、默认模型、视频/短剧任务状态管理
"""

import os
import threading
from .config import get_app_dir

# ---------- 模型选项 ----------
TEXT_MODEL_OPTIONS = {
    'deepseek-v4-flash': 'DeepSeek V4 Flash (推荐)',
    'deepseek-chat': 'DeepSeek Chat',
    'deepseek-reasoner': 'DeepSeek Reasoner',
    'gpt-4o-mini': 'GPT-4o Mini',
    'gpt-4o': 'GPT-4o',
    'qwen-turbo': 'Qwen Turbo',
    'qwen-plus': 'Qwen Plus',
    'doubao-pro-32k': '豆包 Pro 32K',
    'doubao-lite-32k': '豆包 Lite 32K',
}
IMAGE_MODEL_OPTIONS = {
    'agnes-image-2.1-flash': 'Agnes Image 2.1 Flash (推荐)',
    'agnes-image-2.0-flash': 'Agnes Image 2.0 Flash',
    'doubao-seedream-3-0': '豆包 Seedream 3.0',
    'minimax-image-01': 'MiniMax Image 01',
    'qwen-image-plus': 'Qwen Image Plus',
}
VIDEO_MODEL_OPTIONS = {
    'agnes-video-v2.0': 'Agnes Video 2.0 (推荐)',
    'minimax-video-01': 'MiniMax Video 01',
    'doubao-seaweed-t2v': '豆包 Seaweed T2V',
    'qwen-video-gen': 'Qwen Video Gen',
}
DEFAULT_TEXT_MODEL = 'deepseek-v4-flash'
DEFAULT_IMAGE_MODEL = 'agnes-image-2.1-flash'
DEFAULT_VIDEO_MODEL = 'agnes-video-v2.0'

# ---------- 视频任务状态（内存存储，重启后丢失）----------
video_tasks = {}
task_lock = threading.Lock()

# ---------- 短剧任务状态 ----------
drama_tasks = {}
drama_lock = threading.Lock()

def ensure_drama_dirs(drama_id):
    """确保短剧输出目录存在"""
    app_dir = get_app_dir()
    base = os.path.join(app_dir, 'dramas', drama_id)
    for sub in ('images', 'videos'):
        os.makedirs(os.path.join(base, sub), exist_ok=True)
    return base
