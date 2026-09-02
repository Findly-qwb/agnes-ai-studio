"""
视频生成服务模块
包含：文件下载、视频轮询
"""

import os
import json
import time
import uuid
import requests
from datetime import datetime

from ..config import get_app_dir, get_vendor_api_key, get_vendor_base_url, BASE_URL, shutdown_event
from ..models import video_tasks, task_lock

# Agnes Video 2.5 及后续版本使用 OpenAI Videos 兼容新 API（mode/seconds/size），
# 旧模型（v2.0 及第三方）使用 width/height/num_frames 旧协议
NEW_AGNES_VIDEO_MODELS = {'agnes-video-2.5-flash', 'agnes-video-2.5'}


def is_new_video_api(model):
    """判断是否使用 Agnes 新视频 API"""
    return (model or '') in NEW_AGNES_VIDEO_MODELS


def _nearest_aspect_ratio(width, height):
    """根据宽高近似选择画幅"""
    candidates = {'21:9': 21/9, '16:9': 16/9, '4:3': 4/3, '1:1': 1.0, '3:4': 3/4, '9:16': 9/16}
    target = width / height
    return min(candidates, key=lambda k: abs(candidates[k] - target))


def build_video_payload(model, prompt, image_url='', negative_prompt='', width=1152, height=768, num_frames=121, frame_rate=24, images=None):
    """构建视频请求 payload，兼容新旧 API 格式"""
    print(f"[视频参数] 模型={model} num_frames={num_frames} frame_rate={frame_rate} width={width} height={height} "
          f"有参考图={bool(image_url or images)} 负面词={bool(negative_prompt)}")
    if is_new_video_api(model):
        seconds = str(max(4, min(12, round(num_frames / frame_rate))))
        payload = {
            'model': model,
            'prompt': prompt,
            'mode': 'reference' if (image_url or images) else 'text',
            'seconds': seconds,
            'size': '720P',
            'aspect_ratio': _nearest_aspect_ratio(width, height),
        }
        ref_imgs = list(images or []) + ([image_url] if image_url else [])
        if ref_imgs:
            payload['images'] = ref_imgs[:5]
        print(f"[视频参数] 新API换算 seconds={seconds} mode={payload['mode']} aspect_ratio={payload['aspect_ratio']} => 提交payload: {payload}")
        return payload
    payload = {
        'model': model,
        'prompt': prompt,
        'width': width,
        'height': height,
        'num_frames': num_frames,
        'frame_rate': frame_rate,
    }
    if image_url:
        payload['image'] = image_url
    if negative_prompt:
        payload['negative_prompt'] = negative_prompt
    return payload


def query_video_task(model, base_url, headers, task_id=None, video_id=None):
    """查询视频任务状态，兼容新旧 API"""
    print(f"[视频轮询] 模型={model} task_id={task_id} video_id={str(video_id)[:40] if video_id else None} base_url={base_url}")
    if is_new_video_api(model) and video_id:
        return requests.get(f'{base_url}/agnesapi', headers=headers,
                            params={'video_id': video_id, 'model_name': model}, timeout=30)
    return requests.get(f'{base_url}/videos/{task_id}', headers=headers, timeout=30)


def download_video_by_video_id(video_id, base_url, headers, subdir, prefix, model=None):
    """通过 video_id 使用 /agnesapi 端点下载视频

    Args:
        video_id: 视频 ID
        base_url: API Base URL
        headers: 请求头
        subdir: 保存子目录
        prefix: 文件名前缀
        model: 模型名（新 API 查询时建议携带）

    Returns:
        保存后的文件名，失败返回 None
    """
    try:
        print(f"[视频下载] 通过 video_id 获取视频: {video_id[:50]}...")
        # 尝试新端点 /agnesapi?video_id=<VIDEO_ID>
        agnesapi_url = f'{base_url}/agnesapi'
        params = {'video_id': video_id}
        if model:
            params['model_name'] = model
        resp = requests.get(agnesapi_url, headers=headers, params=params, timeout=(30, 120), stream=True)
        
        if resp.status_code == 200:
            content_type = resp.headers.get('Content-Type', '')
            # 如果返回的是直接的视频流
            if 'video' in content_type or 'octet-stream' in content_type:
                return _save_stream_to_file(resp, subdir, prefix)
            # 如果返回的是 JSON（包含下载 URL）
            try:
                data = resp.json()
                url = (data.get('url', '') or data.get('video_url', '') or 
                       data.get('video', '') or data.get('output_url', ''))
                if isinstance(data.get('data'), dict):
                    url = url or data['data'].get('url', '') or data['data'].get('video_url', '')
                if url:
                    print(f"[视频下载] agnesapi 返回 URL: {url[:150]}...")
                    return download_and_save_file(url, subdir, prefix, 'mp4')
                # 可能 data 本身就是视频数据（base64）
                if data.get('data') and isinstance(data['data'], str) and len(data['data']) > 1000:
                    import base64
                    app_dir = get_app_dir()
                    target_dir = os.path.join(app_dir, subdir)
                    os.makedirs(target_dir, exist_ok=True)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    short_uuid = uuid.uuid4().hex[:8]
                    filename = f"{prefix}_{timestamp}_{short_uuid}.mp4"
                    filepath = os.path.join(target_dir, filename)
                    with open(filepath, 'wb') as f:
                        f.write(base64.b64decode(data['data']))
                    file_size = os.path.getsize(filepath)
                    if file_size > 1000:
                        print(f"[保存成功] {subdir}/{filename} ({file_size // 1024}KB)")
                        return filename
            except (json.JSONDecodeError, ValueError):
                pass
        else:
            print(f"[视频下载] agnesapi 端点返回 {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[视频下载] agnesapi 端点异常: {type(e).__name__}: {e}")
    return None


def _save_stream_to_file(resp, subdir, prefix):
    """将流式响应保存为文件"""
    app_dir = get_app_dir()
    target_dir = os.path.join(app_dir, subdir)
    os.makedirs(target_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    short_uuid = uuid.uuid4().hex[:8]
    filename = f"{prefix}_{timestamp}_{short_uuid}.mp4"
    filepath = os.path.join(target_dir, filename)
    with open(filepath, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    file_size = os.path.getsize(filepath)
    if file_size > 1000:
        print(f"[保存成功] {subdir}/{filename} ({file_size // 1024}KB)")
        return filename
    else:
        os.remove(filepath)
        return None


def download_and_save_file(url, subdir, prefix, ext, max_retries=3):
    """从 URL 下载文件并保存到本地目录（支持重试）
    
    Args:
        url: 文件下载 URL
        subdir: 子目录名 ('videos' 或 'pictures')
        prefix: 文件名前缀
        ext: 文件扩展名
        max_retries: 最大重试次数
    
    Returns:
        保存后的文件名，失败返回 None
    """
    app_dir = get_app_dir()
    target_dir = os.path.join(app_dir, subdir)
    os.makedirs(target_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    short_uuid = uuid.uuid4().hex[:8]
    filename = f"{prefix}_{timestamp}_{short_uuid}.{ext}"
    filepath = os.path.join(target_dir, filename)

    # 总下载超时（秒）
    total_timeout = 300 if ext == 'mp4' else 120

    for attempt in range(max_retries):
        try:
            print(f"[下载] {subdir}/{filename} (尝试 {attempt+1}/{max_retries}) url={url[:100]}...")
            resp = requests.get(url, timeout=(30, 60), stream=True)  # 连接超时30s，读取超时60s
            resp.raise_for_status()

            content_type = resp.headers.get('Content-Type', '')
            if ext == 'mp4' and 'video' not in content_type and 'octet-stream' not in content_type and 'mp4' not in content_type:
                print(f"[下载警告] Content-Type 不是视频: {content_type}")

            total_size = int(resp.headers.get('Content-Length', 0))
            if total_size > 0:
                print(f"[下载] 预期文件大小: {total_size // 1024}KB")
            
            downloaded = 0
            start_time = time.time()
            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if shutdown_event and shutdown_event.is_set():
                        print(f"[下载] 收到关闭信号，停止下载")
                        return None
                    # 检查总超时
                    if time.time() - start_time > total_timeout:
                        print(f"[下载] 总下载超时({total_timeout}s)，已下载 {downloaded // 1024}KB")
                        raise requests.exceptions.Timeout(f"下载总超时({total_timeout}s)")
                    f.write(chunk)
                    downloaded += len(chunk)

            file_size = os.path.getsize(filepath)
            if file_size < 1000:
                print(f"[下载警告] 文件太小 ({file_size} bytes)，可能是错误响应")
                if attempt < max_retries - 1:
                    os.remove(filepath)
                    time.sleep(2)
                    continue
                else:
                    os.remove(filepath)
                    return None

            elapsed = time.time() - start_time
            print(f"[保存成功] {subdir}/{filename} ({file_size // 1024}KB, {elapsed:.1f}s)")
            return filename
        except Exception as e:
            print(f"[下载失败] {subdir}/{filename} 尝试{attempt+1}: {type(e).__name__}: {e}")
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except:
                    pass
            if attempt < max_retries - 1:
                time.sleep(3)
    return None


def extract_video_url(result):
    """从任务响应 JSON 提取视频 URL（多字段兼容）"""
    url = (result.get('video_url') or result.get('url') or result.get('output_url')
           or result.get('video') or '')
    if not url and isinstance(result.get('data'), dict):
        url = result['data'].get('url', '') or result['data'].get('video_url', '')
    return url


def download_generated_video(video_model, base_url, headers, task_id, video_id,
                             video_url, save_subdir, prefix):
    """下载已完成的云端视频：URL → content 端点 → video_id 三路回退，返回文件名或 None"""
    local = None
    if video_url:
        local = download_and_save_file(video_url, save_subdir, prefix, 'mp4')
    if not local:
        try:
            cr = requests.get(f'{base_url}/videos/{task_id}/content', headers=headers, timeout=30)
            if cr.status_code == 200:
                cd = cr.json()
                c_url = (cd.get('url') or cd.get('video_url') or cd.get('video') or '')
                if not c_url and isinstance(cd.get('data'), dict):
                    c_url = cd['data'].get('url', '') or cd['data'].get('video_url', '')
                if c_url:
                    local = download_and_save_file(c_url, save_subdir, prefix, 'mp4')
        except Exception:
            pass
    if not local and video_id:
        local = download_video_by_video_id(video_id, base_url, headers, save_subdir, prefix, video_model)
    return local


def run_video_job(video_model, prompt, primary_image='', extra_images=None, num_frames=121,
                  frame_rate=24, api_key='', negative_prompt='', width=768, height=1152,
                  save_subdir='videos', prefix='shot', abort_check=None, on_submit=None):
    """提交单个视频任务并轮询等待完成，随后下载保存。

    Args:
        abort_check: 可选回调，返回 True 时中止（返回 error='已中止'）
        on_submit: 可选回调，提交成功拿到 task_id 瞬间收到 {'task_id', 'video_id'}

    Returns:
        {'ok': bool, 'local_file': str|None, 'video_url': str, 'error': str}
    """
    base_url = get_vendor_base_url(video_model)
    key = get_vendor_api_key(video_model, fallback_key=api_key)
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    payload = build_video_payload(
        video_model, prompt, image_url=primary_image, images=extra_images or [],
        width=width, height=height, num_frames=num_frames, frame_rate=frame_rate,
        negative_prompt=negative_prompt)

    # 提交（带重试；遇到不支持 negative_prompt 自动移除）
    vtask_id, v_video_id = None, ''
    use_negative = bool(negative_prompt)
    for attempt in range(4):
        if abort_check and abort_check():
            return {'ok': False, 'local_file': None, 'video_url': '', 'error': '已中止'}
        try:
            resp = requests.post(f'{base_url}/videos', headers=headers, json=payload, timeout=120)
        except requests.exceptions.RequestException as e:
            if attempt < 3:
                wait = 30 * (attempt + 1)
                print(f"[视频任务] {prefix} 提交异常({type(e).__name__})，{wait}s 后重试 ({attempt+1}/4)")
                time.sleep(wait)
                continue
            return {'ok': False, 'local_file': None, 'video_url': '', 'error': f'提交失败({type(e).__name__}): {str(e)[:200]}'}
        if resp.status_code == 200:
            vdata = resp.json()
            vtask_id = vdata.get('task_id') or vdata.get('id')
            v_video_id = vdata.get('video_id', '')
            break
        elif resp.status_code == 400 and use_negative and 'negative' in resp.text.lower():
            payload.pop('negative_prompt', None)
            use_negative = False
            continue
        elif resp.status_code in (429, 503, 433) and attempt < 3:
            wait = 30 * (attempt + 1)
            print(f"[视频任务] {prefix} 队列满/限流({resp.status_code})，等待 {wait}s 重试 ({attempt+1}/4)")
            time.sleep(wait)
            continue
        else:
            return {'ok': False, 'local_file': None, 'video_url': '', 'error': f'API {resp.status_code}: {resp.text[:300]}'}
    if not vtask_id:
        return {'ok': False, 'local_file': None, 'video_url': '', 'error': '视频任务提交失败'}
    print(f"[视频任务] {prefix} 已提交 task_id={vtask_id}")
    if on_submit:
        try:
            on_submit({'task_id': vtask_id, 'video_id': v_video_id})
        except Exception as e:
            print(f"[视频任务] on_submit 回调异常: {e}")

    # 轮询（10s × 120 = 20 分钟上限）
    v_url = ''
    for _ in range(120):
        if shutdown_event.wait(timeout=10):
            return {'ok': False, 'local_file': None, 'video_url': '', 'error': '服务关闭'}
        if abort_check and abort_check():
            return {'ok': False, 'local_file': None, 'video_url': '', 'error': '已中止'}
        try:
            poll = query_video_task(video_model, base_url, headers, task_id=vtask_id, video_id=v_video_id)
            if poll.status_code != 200:
                continue
            pr = poll.json()
            st = pr.get('status', '')
            if st == 'completed':
                v_url = extract_video_url(pr)
                v_video_id = pr.get('video_id', '') or v_video_id
                break
            elif st == 'failed':
                return {'ok': False, 'local_file': None, 'video_url': '', 'error': pr.get('error', '生成失败')}
        except Exception as e:
            print(f"[视频任务] 轮询异常: {e}")
            continue
    else:
        return {'ok': False, 'local_file': None, 'video_url': '', 'error': '轮询超时(20分钟)'}

    # 下载三路回退：URL → content 端点 → video_id
    local = download_generated_video(video_model, base_url, headers, vtask_id,
                                     v_video_id, v_url, save_subdir, prefix)
    if not local:
        return {'ok': False, 'local_file': None, 'video_url': v_url, 'error': '视频下载失败'}
    return {'ok': True, 'local_file': local, 'video_url': v_url, 'error': ''}


def poll_video_status(task_id, api_key, model=None, video_id=None):
    """后台轮询视频生成状态"""
    headers = {'Authorization': f'Bearer {api_key}'}
    base_url = get_vendor_base_url(model) if model else BASE_URL
    max_polls = 120
    poll_interval = 10

    for i in range(max_polls):
        if shutdown_event.wait(timeout=poll_interval):
            print(f"[轮询] 收到关闭信号，退出轮询 task_id={task_id}")
            return
        try:
            resp = query_video_task(model, base_url, headers, task_id=task_id, video_id=video_id)

            if resp.status_code == 200:
                result = resp.json()
                status = result.get('status', '')

                with task_lock:
                    if task_id in video_tasks:
                        video_tasks[task_id]['status'] = status

                        if status == 'completed':
                            raw_result = json.dumps(result)
                            print(f"[视频完成] task_id={task_id}, 原始响应: {raw_result}")

                            video_url = (
                                result.get('video_url')
                                or result.get('url')
                                or result.get('output_url')
                                or result.get('video')
                                or result.get('remixed_from_video_id')
                                or ''
                            )
                            if not video_url and isinstance(result.get('data'), dict):
                                video_url = result['data'].get('url', '') or result['data'].get('video_url', '') or result['data'].get('video', '')
                            if not video_url and isinstance(result.get('data'), list) and len(result['data']) > 0:
                                video_url = result['data'][0].get('url', '') or result['data'][0].get('video_url', '')
                            if not video_url and isinstance(result.get('metadata'), dict):
                                meta = result['metadata']
                                video_url = meta.get('video_url', '') or meta.get('url', '') or meta.get('output_url', '')
                            if not video_url:
                                try:
                                    content_resp = requests.get(f'{base_url}/videos/{task_id}/content', headers=headers, timeout=30)
                                    if content_resp.status_code == 200:
                                        content_data = content_resp.json()
                                        video_url = content_data.get('url', '') or content_data.get('video_url', '') or content_data.get('video', '')
                                        if not video_url and isinstance(content_data.get('data'), dict):
                                            video_url = content_data['data'].get('url', '') or content_data['data'].get('video_url', '')
                                        print(f"[视频URL] 通过 content 端点获取: {video_url[:150] if video_url else '(无)'}")
                                except Exception as e2:
                                    print(f"[视频URL] content 端点请求失败: {e2}")

                            print(f"[视频URL] {video_url or '(未获取到)'}")

                            local_filename = None
                            if video_url:
                                local_filename = download_and_save_file(
                                    video_url, 'videos', 'video', 'mp4'
                                )
                            elif result.get('video_id'):
                                # 新 API 格式：通过 video_id 下载
                                video_id = result['video_id']
                                print(f"[视频下载] 使用 video_id: {video_id[:50]}...")
                                local_filename = download_video_by_video_id(
                                    video_id, base_url, headers, 'videos', 'video', model
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
            if shutdown_event.is_set():
                return
            continue
