#!/usr/bin/env python3
"""
Agnes AI Studio - 图片 & 视频生成可视化工具
后端服务 (Flask) - 支持 PyInstaller 打包为独立 .exe
"""

import os
import sys
import json
import time
import uuid
import base64
import threading
import webbrowser
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory

# ==================== PyInstaller 路径处理 ====================
def get_base_path():
    """获取程序基础路径（兼容 PyInstaller 打包和开发模式）"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_config_path():
    """获取配置文件路径（保存在 exe 同级目录，而非临时目录）"""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'config.json')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

# ==================== 路径工具 ====================
def get_app_dir():
    """获取应用程序所在目录（用于保存输出文件）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def ensure_output_dirs():
    """确保输出目录存在"""
    app_dir = get_app_dir()
    videos_dir = os.path.join(app_dir, 'videos')
    pictures_dir = os.path.join(app_dir, 'pictures')
    os.makedirs(videos_dir, exist_ok=True)
    os.makedirs(pictures_dir, exist_ok=True)
    return videos_dir, pictures_dir

def resolve_image_url(image_url):
    """
    处理图片 URL：如果是本地 /pictures/ 路径，转为 base64 data URL；
    否则直接返回原 URL。
    """
    if not image_url:
        return image_url

    # 检查是否是本地 pictures 路径
    if image_url.startswith('/pictures/') or image_url.startswith('pictures/'):
        app_dir = get_app_dir()
        # 提取文件名
        filename = image_url.replace('/pictures/', '').replace('pictures/', '')
        filepath = os.path.join(app_dir, 'pictures', filename)

        if os.path.exists(filepath):
            ext = os.path.splitext(filename)[1].lower()
            mime_map = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                '.bmp': 'image/bmp'
            }
            mime = mime_map.get(ext, 'image/png')
            with open(filepath, 'rb') as f:
                b64_data = base64.b64encode(f.read()).decode('utf-8')
            return f'data:{mime};base64,{b64_data}'
        else:
            print(f"[警告] 本地图片不存在: {filepath}")
            return image_url

    # 也处理完整的本地 URL（如 http://localhost:xxxx/pictures/xxx）
    if '/pictures/' in image_url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(image_url)
            path = parsed.path
            if path.startswith('/pictures/'):
                filename = path.replace('/pictures/', '')
                app_dir = get_app_dir()
                filepath = os.path.join(app_dir, 'pictures', filename)
                if os.path.exists(filepath):
                    ext = os.path.splitext(filename)[1].lower()
                    mime_map = {
                        '.png': 'image/png',
                        '.jpg': 'image/jpeg',
                        '.jpeg': 'image/jpeg',
                        '.gif': 'image/gif',
                        '.webp': 'image/webp',
                        '.bmp': 'image/bmp'
                    }
                    mime = mime_map.get(ext, 'image/png')
                    with open(filepath, 'rb') as f:
                        b64_data = base64.b64encode(f.read()).decode('utf-8')
                    return f'data:{mime};base64,{b64_data}'
        except Exception:
            pass

    return image_url

# ==================== Flask 应用 ====================
app = Flask(
    __name__,
    static_folder=os.path.join(get_base_path(), 'static'),
    static_url_path=''
)

# 注册本地输出目录的静态文件服务
@app.route('/videos/<path:filename>')
def serve_video(filename):
    videos_dir, _ = ensure_output_dirs()
    return send_from_directory(videos_dir, filename)

@app.route('/pictures/<path:filename>')
def serve_picture(filename):
    _, pictures_dir = ensure_output_dirs()
    return send_from_directory(pictures_dir, filename)

# ==================== 配置 ====================
BASE_URL = "https://apihub.agnes-ai.com/v1"

# 存储视频任务状态 (内存存储，重启后丢失)
video_tasks = {}
task_lock = threading.Lock()

# ==================== 路由 ====================

@app.route('/')
def index():
    """返回前端页面"""
    return send_from_directory(
        os.path.join(get_base_path(), 'static'),
        'index.html'
    )


@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """获取/保存 API Key 配置"""
    config_file = get_config_path()
    if request.method == 'GET':
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 返回时隐藏部分 key
            key = data.get('api_key', '')
            data['api_key_masked'] = key[:8] + '****' + key[-4:] if len(key) > 12 else '****'
            data['api_key'] = ''  # 不返回完整 key
            return jsonify(data)
        return jsonify({'api_key': '', 'api_key_masked': ''})

    elif request.method == 'POST':
        data = request.get_json()
        api_key = data.get('api_key', '').strip()
        if api_key:
            config = {'api_key': api_key}
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f)
            return jsonify({'success': True, 'message': 'API Key 已保存'})
        return jsonify({'success': False, 'message': 'API Key 不能为空'}), 400


def get_api_key():
    """读取保存的 API Key"""
    config_file = get_config_path()
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('api_key', '')
    return ''


# ==================== 图片生成 ====================

@app.route('/api/image/generate', methods=['POST'])
def generate_image():
    """文生图"""
    data = request.get_json()
    api_key = get_api_key()
    if not api_key:
        return jsonify({'success': False, 'error': '请先配置 API Key'}), 401

    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'success': False, 'error': '请输入图片描述'}), 400

    size = data.get('size', '1024x1024')
    model = data.get('model', 'agnes-image-2.1-flash')
    save_local = data.get('save_local', True)

    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': model,
            'prompt': prompt,
            'size': size
        }

        resp = requests.post(
            f'{BASE_URL}/images/generations',
            headers=headers,
            json=payload,
            timeout=120
        )

        if resp.status_code == 200:
            result = resp.json()
            image_url = None
            if 'data' in result and len(result['data']) > 0:
                image_url = result['data'][0].get('url')

            # 下载并保存到本地 pictures 目录
            local_filename = None
            if save_local and image_url:
                local_filename = _download_and_save_file(
                    image_url, 'pictures', 'image', 'png'
                )

            return jsonify({
                'success': True,
                'image_url': image_url,
                'local_file': local_filename,
                'raw_response': result
            })
        else:
            return jsonify({
                'success': False,
                'error': f'API 错误 ({resp.status_code}): {resp.text}'
            }), resp.status_code

    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': '请求超时，请重试'}), 504
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/image/img2img', methods=['POST'])
def img2img():
    """图生图 / 图片编辑"""
    data = request.get_json()
    api_key = get_api_key()
    if not api_key:
        return jsonify({'success': False, 'error': '请先配置 API Key'}), 401

    prompt = data.get('prompt', '').strip()
    image_url = data.get('image_url', '').strip()
    if not prompt or not image_url:
        return jsonify({'success': False, 'error': '请输入描述和图片URL'}), 400

    # 将本地图片路径转为 base64
    image_url = resolve_image_url(image_url)

    size = data.get('size', '1024x768')
    save_local = data.get('save_local', True)

    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': 'agnes-image-2.0-flash',
            'prompt': prompt,
            'size': size,
            'extra_body': {
                'tags': ['img2img'],
                'image': [image_url],
                'response_format': 'url'
            }
        }

        resp = requests.post(
            f'{BASE_URL}/images/generations',
            headers=headers,
            json=payload,
            timeout=120
        )

        if resp.status_code == 200:
            result = resp.json()
            image_url_out = None
            if 'data' in result and len(result['data']) > 0:
                image_url_out = result['data'][0].get('url')

            # 下载并保存到本地 pictures 目录
            local_filename = None
            if save_local and image_url_out:
                local_filename = _download_and_save_file(
                    image_url_out, 'pictures', 'edited_image', 'png'
                )

            return jsonify({
                'success': True,
                'image_url': image_url_out,
                'local_file': local_filename,
                'raw_response': result
            })
        else:
            return jsonify({
                'success': False,
                'error': f'API 错误 ({resp.status_code}): {resp.text}'
            }), resp.status_code

    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': '请求超时，请重试'}), 504
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 视频生成 ====================

@app.route('/api/video/generate', methods=['POST'])
def generate_video():
    """提交视频生成任务"""
    data = request.get_json()
    api_key = get_api_key()
    if not api_key:
        return jsonify({'success': False, 'error': '请先配置 API Key'}), 401

    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'success': False, 'error': '请输入视频描述'}), 400

    width = data.get('width', 1152)
    height = data.get('height', 768)
    num_frames = data.get('num_frames', 121)
    frame_rate = data.get('frame_rate', 24)
    image_url = data.get('image_url', '')  # 可选：图生视频
    # 将本地图片路径转为 base64
    if image_url:
        image_url = resolve_image_url(image_url)
    negative_prompt = data.get('negative_prompt', '')
    seed = data.get('seed')

    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': 'agnes-video-v2.0',
            'prompt': prompt,
            'width': width,
            'height': height,
            'num_frames': num_frames,
            'frame_rate': frame_rate
        }

        if image_url:
            payload['image'] = image_url
        if negative_prompt:
            payload['negative_prompt'] = negative_prompt
        if seed is not None:
            payload['seed'] = seed

        resp = requests.post(
            f'{BASE_URL}/videos',
            headers=headers,
            json=payload,
            timeout=60
        )

        if resp.status_code == 200:
            result = resp.json()
            task_id = result.get('task_id')
            video_id = result.get('video_id')

            # 保存任务信息
            with task_lock:
                video_tasks[task_id] = {
                    'task_id': task_id,
                    'video_id': video_id,
                    'status': 'queued',
                    'prompt': prompt,
                    'created_at': time.time(),
                    'result': None
                }

            # 启动后台轮询
            thread = threading.Thread(
                target=poll_video_status,
                args=(task_id, api_key),
                daemon=True
            )
            thread.start()

            return jsonify({
                'success': True,
                'task_id': task_id,
                'video_id': video_id,
                'status': 'queued',
                'message': '视频任务已提交，正在排队处理...'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'API 错误 ({resp.status_code}): {resp.text}'
            }), resp.status_code

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _download_and_save_file(url, subdir, prefix, ext):
    """从 URL 下载文件并保存到本地目录
    
    Args:
        url: 文件下载 URL
        subdir: 子目录名 ('videos' 或 'pictures')
        prefix: 文件名前缀
        ext: 文件扩展名
    
    Returns:
        保存后的文件名，失败返回 None
    """
    try:
        app_dir = get_app_dir()
        target_dir = os.path.join(app_dir, subdir)
        os.makedirs(target_dir, exist_ok=True)

        # 生成唯一文件名：前缀_时间戳_UUID.扩展名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        short_uuid = uuid.uuid4().hex[:8]
        filename = f"{prefix}_{timestamp}_{short_uuid}.{ext}"
        filepath = os.path.join(target_dir, filename)

        # 下载文件
        resp = requests.get(url, timeout=120, stream=True)
        resp.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"[保存] {subdir}/{filename}")
        return filename
    except Exception as e:
        print(f"[保存失败] {subdir}: {e}")
        return None


def poll_video_status(task_id, api_key):
    """后台轮询视频生成状态"""
    headers = {'Authorization': f'Bearer {api_key}'}
    max_polls = 120  # 最多轮询 120 次
    poll_interval = 10  # 每 10 秒轮询一次

    for i in range(max_polls):
        time.sleep(poll_interval)
        try:
            # 方式1：推荐的方式
            resp = requests.get(
                f'https://apihub.agnes-ai.com/agnesapi',
                params={'video_id': task_id},
                headers=headers,
                timeout=30
            )

            if resp.status_code != 200:
                # 方式2：兼容旧版
                resp = requests.get(
                    f'{BASE_URL}/videos/{task_id}',
                    headers=headers,
                    timeout=30
                )

            if resp.status_code == 200:
                result = resp.json()
                status = result.get('status', '')

                with task_lock:
                    if task_id in video_tasks:
                        video_tasks[task_id]['status'] = status

                        if status == 'completed':
                            # 兼容多种可能的字段名
                            raw_result = json.dumps(result)
                            print(f"[视频完成] task_id={task_id}, 原始响应: {raw_result}")

                            video_url = (
                                result.get('video_url') or
                                result.get('url') or
                                result.get('output_url') or
                                result.get('data', {}).get('url') if isinstance(result.get('data'), dict) else None or
                                result.get('remixed_from_video_id') or
                                ''
                            )
                            # 如果 result.data 是列表形式
                            if not video_url and isinstance(result.get('data'), list) and len(result['data']) > 0:
                                video_url = result['data'][0].get('url', '') or result['data'][0].get('video_url', '')

                            print(f"[视频URL] {video_url or '(未获取到)'}")

                            # 下载视频到本地 videos 目录
                            local_filename = None
                            if video_url:
                                local_filename = _download_and_save_file(
                                    video_url, 'videos', 'video', 'mp4'
                                )

                            video_tasks[task_id]['result'] = {
                                'video_url': video_url,
                                'local_file': local_filename,
                                'raw_response': result
                            }
                            break
                        elif status == 'failed':
                            video_tasks[task_id]['result'] = {
                                'error': result.get('error', '生成失败')
                            }
                            break
        except Exception as e:
            continue


@app.route('/api/video/status/<task_id>', methods=['GET'])
def get_video_status(task_id):
    """查询视频任务状态"""
    with task_lock:
        task = video_tasks.get(task_id)
        if not task:
            return jsonify({'success': False, 'error': '任务不存在'}), 404

        response = {
            'success': True,
            'task_id': task['task_id'],
            'status': task['status'],
            'prompt': task['prompt'],
            'created_at': task['created_at']
        }

        if task['status'] == 'completed':
            response['video_url'] = task['result'].get('video_url', '')
            response['local_file'] = task['result'].get('local_file', '')
            response['raw_response'] = task['result'].get('raw_response', {})
        elif task['status'] == 'failed':
            response['error'] = task['result'].get('error', '生成失败')

        return jsonify(response)


@app.route('/api/video/tasks', methods=['GET'])
def list_video_tasks():
    """列出所有视频任务"""
    with task_lock:
        tasks = []
        for task_id, task in video_tasks.items():
            t = {
                'task_id': task['task_id'],
                'status': task['status'],
                'prompt': task['prompt'][:50] + '...' if len(task['prompt']) > 50 else task['prompt'],
                'created_at': task['created_at']
            }
            if task['status'] == 'completed' and task.get('result'):
                t['video_url'] = task['result'].get('video_url', '')
                t['local_file'] = task['result'].get('local_file', '')
            tasks.append(t)
        return jsonify({'success': True, 'tasks': tasks})


# ==================== 图片上传 API ====================

@app.route('/api/upload/image', methods=['POST'])
def upload_image():
    """上传本地图片，返回可访问的 URL"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '未找到上传文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '文件名为空'}), 400

    # 检查文件类型
    ext = os.path.splitext(file.filename)[1].lower()
    allowed_exts = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
    if ext not in allowed_exts:
        return jsonify({'success': False, 'error': f'不支持的图片格式: {ext}'}), 400

    # 保存到 pictures 目录
    _, pictures_dir = ensure_output_dirs()
    unique_name = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
    save_path = os.path.join(pictures_dir, unique_name)
    file.save(save_path)

    # 返回可访问的 URL
    return jsonify({
        'success': True,
        'filename': unique_name,
        'url': f'/pictures/{unique_name}'
    })


# ==================== 文件列表 API ====================

@app.route('/api/files/<subdir>', methods=['GET'])
def list_files(subdir):
    """列出本地已生成的文件"""
    if subdir not in ('videos', 'pictures'):
        return jsonify({'success': False, 'error': '无效目录'}), 400

    app_dir = get_app_dir()
    target_dir = os.path.join(app_dir, subdir)
    if not os.path.exists(target_dir):
        return jsonify({'success': True, 'files': []})

    files = []
    for f in sorted(os.listdir(target_dir), reverse=True):
        filepath = os.path.join(target_dir, f)
        if os.path.isfile(filepath):
            stat = os.stat(filepath)
            files.append({
                'filename': f,
                'url': f'/{subdir}/{f}',
                'size': stat.st_size,
                'size_display': _format_size(stat.st_size),
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })

    return jsonify({'success': True, 'files': files})


def _format_size(size_bytes):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ==================== 启动 ====================

def main():
    """主入口"""
    print("=" * 60)
    print("  Agnes AI Studio - 图片 & 视频生成可视化工具 v1.0")
    print("  项目目录: " + os.path.dirname(get_config_path()))
    print("=" * 60)
    print("  本地访问: http://127.0.0.1:5000")
    print("  局域网访问: http://你的IP地址:5000")
    print("  按 Ctrl+C 停止服务")
    print("=" * 60)

    # 自动打开浏览器
    threading.Timer(1.5, lambda: webbrowser.open('http://127.0.0.1:5000')).start()

    # 生产模式运行（不开启 debug，避免 reloader 冲突）
    app.run(host='0.0.0.0', port=5000, debug=False)


if __name__ == '__main__':
    main()
