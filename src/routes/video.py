"""
视频生成路由
"""

import time
import json
import threading
import requests
from flask import Blueprint, request, jsonify

from ..config import get_vendor_api_key, get_vendor_base_url, resolve_image_url
from ..models import video_tasks, task_lock
from ..services.video_gen import poll_video_status, build_video_payload

video_bp = Blueprint('video', __name__)


@video_bp.route('/api/video/generate', methods=['POST'])
def generate_video():
    """提交视频生成任务"""
    data = request.get_json()
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'success': False, 'error': '请输入视频描述'}), 400

    width = data.get('width', 1152)
    height = data.get('height', 768)
    num_frames = data.get('num_frames', 121)
    frame_rate = data.get('frame_rate', 24)
    image_url = data.get('image_url', '')
    model = data.get('model', 'agnes-video-v2.0')
    if image_url:
        image_url = resolve_image_url(image_url)
    negative_prompt = data.get('negative_prompt', '')
    seed = data.get('seed')
    
    api_key = get_vendor_api_key(model)
    if not api_key:
        return jsonify({'success': False, 'error': '请先配置 API Key'}), 401
    base_url = get_vendor_base_url(model)

    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        payload = build_video_payload(
            model, prompt, image_url=image_url, negative_prompt=negative_prompt,
            width=width, height=height, num_frames=num_frames, frame_rate=frame_rate
        )

        if seed is not None:
            payload['seed'] = seed

        print(f"[视频提交] POST {base_url}/videos header_authorization={'Bearer '+api_key[:8]+'...' if api_key else '(空)'} params={json.dumps(payload, ensure_ascii=False)}")
        resp = requests.post(
            f'{base_url}/videos',
            headers=headers,
            json=payload,
            timeout=60
        )

        if resp.status_code == 200:
            result = resp.json()
            task_id = result.get('task_id') or result.get('id')
            video_id = result.get('video_id')

            with task_lock:
                video_tasks[task_id] = {
                    'task_id': task_id,
                    'video_id': video_id,
                    'status': 'queued',
                    'prompt': prompt,
                    'created_at': time.time(),
                    'result': None
                }

            thread = threading.Thread(
                target=poll_video_status,
                args=(task_id, api_key, model, video_id),
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


@video_bp.route('/api/video/status/<task_id>', methods=['GET'])
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


@video_bp.route('/api/video/tasks', methods=['GET'])
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
