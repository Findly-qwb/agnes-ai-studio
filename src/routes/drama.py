"""
短剧生成路由 + 流水线
"""

import os
import json
import time
import uuid
import threading
import requests
from flask import Blueprint, request, jsonify

from ..config import (
    get_api_key, get_app_dir, get_vendor_api_key, get_vendor_base_url, shutdown_event
)
from ..models import (
    drama_tasks, drama_lock, ensure_drama_dirs,
    TEXT_MODEL_OPTIONS, IMAGE_MODEL_OPTIONS, VIDEO_MODEL_OPTIONS,
    DEFAULT_TEXT_MODEL, DEFAULT_IMAGE_MODEL, DEFAULT_VIDEO_MODEL
)
from ..services.text_model import (
    call_text_model, parse_json_from_text,
    script_system_prompt, storyboard_system_prompt, assets_system_prompt,
    build_video_prompt
)
from ..services.video_gen import download_and_save_file
from ..services.video_merge import merge_videos

drama_bp = Blueprint('drama', __name__)


# ==================== 短剧流水线 ====================

def drama_pipeline(drama_id, api_key, text_api_key=None):
    """短剧生成 5 步流水线（后台线程执行）"""
    if text_api_key is None:
        text_api_key = api_key

    def _update(**kwargs):
        with drama_lock:
            if drama_id in drama_tasks:
                drama_tasks[drama_id].update(kwargs)

    def _is_shutdown():
        return shutdown_event.is_set()

    try:
        # ---- Step 1: 生成剧本 ----
        print(f"[短剧 {drama_id}] Step 1: 生成剧本...")
        _update(status='step1', step='step1', message='正在生成剧本...')
        if _is_shutdown(): return

        try:
            text_model = drama_tasks[drama_id].get('text_model', DEFAULT_TEXT_MODEL)
            script_text = call_text_model(
                script_system_prompt(),
                f"请根据以下描述生成一个短剧剧本：\n{drama_tasks[drama_id]['prompt']}",
                text_api_key,
                model=text_model
            )
            script = parse_json_from_text(script_text)
            _update(script=script, message='剧本生成完成')
            print(f"[短剧 {drama_id}] 剧本: {json.dumps(script, ensure_ascii=False)[:200]}")
        except Exception as e:
            _update(status='failed', message=f'剧本生成失败: {e}')
            return

        # ---- Step 2: 生成分镜 ----
        if _is_shutdown(): return
        print(f"[短剧 {drama_id}] Step 2: 生成分镜...")
        _update(status='step2', step='step2', message='正在生成分镜脚本...')

        shot_duration = drama_tasks[drama_id].get('shot_duration', 5)
        try:
            storyboard_text = call_text_model(
                storyboard_system_prompt(shot_duration),
                f"请将以下剧本改写为分镜脚本，每个分镜约{shot_duration}秒：\n{json.dumps(script, ensure_ascii=False)}",
                text_api_key,
                model=text_model
            )
            storyboard = parse_json_from_text(storyboard_text)
            shots = storyboard.get('shots', [])
            _update(storyboard=storyboard, shots=shots, message=f'分镜生成完成，共 {len(shots)} 个镜头')
            print(f"[短剧 {drama_id}] 分镜数: {len(shots)}")
        except Exception as e:
            _update(status='failed', message=f'分镜生成失败: {e}')
            return

        # ---- Step 3: 提取素材 + 生成参考图 ----
        if _is_shutdown(): return
        print(f"[短剧 {drama_id}] Step 3: 提取素材并生成参考图...")
        _update(status='step3', step='step3', message='正在提取角色/场景/道具特征...')

        try:
            assets_text = call_text_model(
                assets_system_prompt(),
                f"请从以下剧本中提取所有角色、场景、道具的视觉特征描述：\n"
                f"剧本：{json.dumps(script, ensure_ascii=False)}\n"
                f"分镜：{json.dumps(storyboard, ensure_ascii=False)}",
                text_api_key,
                model=text_model
            )
            assets = parse_json_from_text(assets_text)
            all_assets = []
            for cat in ('characters', 'scenes', 'props'):
                for item in assets.get(cat, []):
                    all_assets.append({
                        'category': cat,
                        'name': item.get('name', ''),
                        'desc': item.get('desc', ''),
                        'image_url': None,
                        'local_file': None
                    })
            _update(assets=all_assets, message=f'提取到 {len(all_assets)} 个素材，正在生成参考图...')
        except Exception as e:
            _update(status='failed', message=f'素材提取失败: {e}')
            return

        drama_base = ensure_drama_dirs(drama_id)
        for idx, asset in enumerate(all_assets):
            if _is_shutdown(): return
            category = asset.get('category', 'characters')
            cat_label = {'characters': '角色', 'scenes': '场景', 'props': '道具'}.get(category, '素材')
            _update(message=f'生成{cat_label}图 ({idx+1}/{len(all_assets)}): {asset["name"]}...')
            try:
                desc = asset.get('desc', '')
                if category == 'characters':
                    img_prompt = (
                        f"3D anime next-gen character design sheet, cinematic CG quality, ultra-realistic rendering, "
                        f"Unreal Engine 5 style, PBR physical materials, global illumination, volumetric lighting, "
                        f"soft warm-neutral natural light, 8K UHD resolution, realistic human skin (pores, fine texture, "
                        f"natural subsurface scattering), natural cool-tone porcelain white skin, fine matte skin texture, "
                        f"no oiliness or wetness, soft translucent glow. "
                        f"9:16 vertical composition, pure white minimalist background, premium character design board layout. "
                        f"Left side: large-scale front full-body illustration. "
                        f"Right top: front/side/back three-view orthographic. "
                        f"Right middle: one front face close-up, below it 5 small expression close-ups including 1 side face. "
                        f"Left bottom: hand detail showcase (clear fingers, no extra or missing fingers). "
                        f"Right bottom: clothing, accessories, hair detail close-ups. "
                        f"Character description: {desc}. "
                        f"Same character throughout, facial features hairstyle and clothing fully consistent, no deformation, no distortion. "
                        f"Standard standing pose, rigorous structure."
                    )
                    img_size = '768x1344'
                elif category == 'scenes':
                    img_prompt = (
                        f"3D anime next-gen scene design, cinematic CG quality, ultra-realistic rendering, "
                        f"Unreal Engine 5 style, PBR physical materials, global illumination, volumetric lighting, "
                        f"soft warm-neutral natural light, 8K UHD resolution. "
                        f"16:9 horizontal composition, pure white background border. "
                        f"Scene environment design concept art, multiple angles view. "
                        f"Scene description: {desc}. "
                        f"Highly detailed environment, consistent style, no characters."
                    )
                    img_size = '1344x768'
                else:
                    img_prompt = (
                        f"3D anime next-gen prop design sheet, cinematic CG quality, ultra-realistic rendering, "
                        f"Unreal Engine 5 style, PBR physical materials, global illumination, volumetric lighting, "
                        f"soft warm-neutral natural light, 8K UHD resolution. "
                        f"9:16 vertical composition, pure white minimalist background, premium prop design board layout. "
                        f"Multiple views: front, side, back, top, detail close-ups. "
                        f"Material and texture details clearly visible. "
                        f"Prop description: {desc}. "
                        f"Consistent design, no deformation, high detail craftsmanship showcase."
                    )
                    img_size = '768x1344'
                
                image_model = drama_tasks[drama_id].get('image_model', DEFAULT_IMAGE_MODEL)
                img_base_url = get_vendor_base_url(image_model)
                img_api_key = get_vendor_api_key(image_model, fallback_key=api_key)
                headers = {'Authorization': f'Bearer {img_api_key}', 'Content-Type': 'application/json'}
                resp = requests.post(f'{img_base_url}/images/generations', headers=headers,
                    json={'model': image_model, 'prompt': img_prompt, 'size': img_size},
                    timeout=120)
                if resp.status_code == 200:
                    result = resp.json()
                    if 'data' in result and len(result['data']) > 0:
                        image_url = result['data'][0].get('url')
                        asset['image_url'] = image_url
                        if image_url:
                            local = download_and_save_file(image_url, f'dramas/{drama_id}/images', f'asset_{idx}', 'png')
                            asset['local_file'] = local
                        else:
                            print(f"[短剧 {drama_id}] 素材 {idx+1} [{asset['name']}] 警告: data[0] 中无 url 字段，响应: {json.dumps(result, ensure_ascii=False)[:500]}")
                    else:
                        print(f"[短剧 {drama_id}] 素材 {idx+1} [{asset['name']}] 警告: 响应中无 data 字段，响应: {json.dumps(result, ensure_ascii=False)[:500]}")
                else:
                    print(f"[短剧 {drama_id}] 素材 {idx+1} [{asset['name']}] API错误 {resp.status_code}: {resp.text[:500]}")
                print(f"[短剧 {drama_id}] 素材 {idx+1} [{asset['name']}]: {'OK' if asset['image_url'] else 'FAIL'}")
            except Exception as e:
                print(f"[短剧 {drama_id}] 素材 {idx+1} [{asset.get('name', '?')}] 图片生成异常: {type(e).__name__}: {e}")
            with drama_lock:
                drama_tasks[drama_id]['assets'] = list(all_assets)

        _update(message=f'参考图生成完成，{sum(1 for a in all_assets if a["image_url"])}/{len(all_assets)} 成功')

        # ---- Step 4: 逐镜头生成视频 ----
        if _is_shutdown(): return
        print(f"[短剧 {drama_id}] Step 4: 逐镜头生成视频...")
        _update(status='step4', step='step4', message='开始逐镜头生成视频...')

        shot_duration_to_frames = {5: 121, 10: 241, 18: 441}
        num_frames = shot_duration_to_frames.get(shot_duration, 121)
        video_results = []

        for shot_idx, shot in enumerate(shots):
            if _is_shutdown(): return
            _update(message=f'生成视频 ({shot_idx+1}/{len(shots)}): 分镜 {shot.get("shot_index", shot_idx+1)}...')

            shot_chars = [c.lower().strip() for c in shot.get('characters', [])]
            shot_asset_list = []
            primary_image = None
            
            for asset in all_assets:
                if not asset.get('image_url'):
                    continue
                asset_name = asset.get('name', '').lower().strip()
                if any(asset_name in c or c in asset_name for c in shot_chars):
                    shot_asset_list.append(asset)
                    if not primary_image:
                        primary_image = asset['image_url']
            
            for asset in all_assets:
                if not asset.get('image_url') or asset.get('category') != 'scenes':
                    continue
                asset_name = asset.get('name', '').lower().strip()
                scene_desc = shot.get('scene_desc', '').lower()
                if asset_name and asset_name in scene_desc:
                    shot_asset_list.append(asset)
                    if not primary_image:
                        primary_image = asset['image_url']
            
            for asset in all_assets:
                if not asset.get('image_url') or asset.get('category') != 'props':
                    continue
                asset_name = asset.get('name', '').lower().strip()
                action_desc = shot.get('action', '').lower()
                if asset_name and asset_name in action_desc:
                    shot_asset_list.append(asset)
            
            if not primary_image:
                for asset in all_assets:
                    if asset.get('image_url') and asset.get('category') == 'characters':
                        primary_image = asset['image_url']
                        shot_asset_list.append(asset)
                        break

            video_prompt = build_video_prompt(shot, shot_asset_list)

            try:
                video_model = drama_tasks[drama_id].get('video_model', DEFAULT_VIDEO_MODEL)
                vid_base_url = get_vendor_base_url(video_model)
                vid_api_key = get_vendor_api_key(video_model, fallback_key=api_key)
                headers = {'Authorization': f'Bearer {vid_api_key}', 'Content-Type': 'application/json'}
                payload = {
                    'model': video_model, 'prompt': video_prompt,
                    'width': 1152, 'height': 768,
                    'num_frames': num_frames, 'frame_rate': 24
                }
                if primary_image:
                    payload['image'] = primary_image

                resp = requests.post(f'{vid_base_url}/videos', headers=headers, json=payload, timeout=60)
                if resp.status_code != 200:
                    video_results.append({'shot_index': shot.get('shot_index', shot_idx+1), 'status': 'failed',
                        'error': f'API {resp.status_code}: {resp.text}', 'prompt': video_prompt})
                    continue

                vdata = resp.json()
                vtask_id = vdata.get('task_id') or vdata.get('video_id')
                if not vtask_id:
                    video_results.append({'shot_index': shot.get('shot_index', shot_idx+1), 'status': 'failed',
                        'error': '未返回 task_id', 'prompt': video_prompt})
                    continue

                for poll_i in range(120):
                    if _is_shutdown(): return
                    if shutdown_event.wait(timeout=10):
                        return
                    try:
                        pr = requests.get(f'{vid_base_url}/videos/{vtask_id}', headers=headers, timeout=30)
                        if pr.status_code == 200:
                            pr_data = pr.json()
                            v_status = pr_data.get('status', '')
                            if v_status == 'completed':
                                full_resp = json.dumps(pr_data, ensure_ascii=False)
                                print(f"[短剧 {drama_id}] 镜头 {shot_idx+1} 完成，完整响应: {full_resp}")
                                
                                v_url = (pr_data.get('video_url') or pr_data.get('url')
                                    or pr_data.get('output_url') or pr_data.get('video') or '')
                                if not v_url and isinstance(pr_data.get('data'), dict):
                                    v_url = pr_data['data'].get('url', '') or pr_data['data'].get('video_url', '') or pr_data['data'].get('video', '')
                                if not v_url and isinstance(pr_data.get('data'), list) and len(pr_data['data']) > 0:
                                    v_url = pr_data['data'][0].get('url', '') or pr_data['data'][0].get('video_url', '')
                                if not v_url and isinstance(pr_data.get('result'), dict):
                                    v_url = pr_data['result'].get('url', '') or pr_data['result'].get('video_url', '')
                                if not v_url and isinstance(pr_data.get('metadata'), dict):
                                    meta = pr_data['metadata']
                                    v_url = meta.get('video_url', '') or meta.get('url', '') or meta.get('output_url', '')
                                    if not v_url and isinstance(meta.get('size_mapping'), dict):
                                        v_url = meta['size_mapping'].get('video_url', '') or meta['size_mapping'].get('url', '')
                                if not v_url:
                                    try:
                                        content_resp = requests.get(f'{vid_base_url}/videos/{vtask_id}/content', headers=headers, timeout=30)
                                        if content_resp.status_code == 200:
                                            content_data = content_resp.json()
                                            v_url = content_data.get('url', '') or content_data.get('video_url', '') or content_data.get('video', '')
                                            if not v_url and isinstance(content_data.get('data'), dict):
                                                v_url = content_data['data'].get('url', '') or content_data['data'].get('video_url', '')
                                            print(f"[短剧 {drama_id}] 镜头 {shot_idx+1} 通过 content 端点获取URL: {v_url[:150] if v_url else '(无)'}")
                                    except Exception as e2:
                                        print(f"[短剧 {drama_id}] 镜头 {shot_idx+1} content 端点请求失败: {e2}")
                                local_fn = None
                                if v_url:
                                    print(f"[短剧 {drama_id}] 镜头 {shot_idx+1} 视频URL: {v_url[:150]}...")
                                    local_fn = download_and_save_file(v_url, f'dramas/{drama_id}/videos', f'shot_{shot_idx}', 'mp4')
                                else:
                                    print(f"[短剧 {drama_id}] 镜头 {shot_idx+1} 警告: 未提取到视频URL")
                                if local_fn:
                                    video_results.append({
                                        'shot_index': shot.get('shot_index', shot_idx+1),
                                        'status': 'completed', 'video_url': v_url,
                                        'local_file': local_fn, 'prompt': video_prompt
                                    })
                                    print(f"[短剧 {drama_id}] 镜头 {shot_idx+1} 视频保存成功: {local_fn}")
                                else:
                                    video_results.append({
                                        'shot_index': shot.get('shot_index', shot_idx+1),
                                        'status': 'failed',
                                        'error': '视频生成完成但下载失败，请查看控制台日志',
                                        'prompt': video_prompt
                                    })
                                    print(f"[短剧 {drama_id}] 镜头 {shot_idx+1} 视频下载失败")
                                break
                            elif v_status == 'failed':
                                video_results.append({'shot_index': shot.get('shot_index', shot_idx+1),
                                    'status': 'failed', 'error': pr_data.get('error', '生成失败'), 'prompt': video_prompt})
                                break
                    except Exception:
                        continue
            except Exception as e:
                video_results.append({'shot_index': shot.get('shot_index', shot_idx+1), 'status': 'failed',
                    'error': str(e), 'prompt': video_prompt})

            with drama_lock:
                drama_tasks[drama_id]['video_results'] = list(video_results)

        # ---- Step 5: 拼接所有镜头视频 ----
        completed_count = sum(1 for v in video_results if v["status"] == "completed")
        if completed_count >= 2:
            _update(status='merging', step='merging', message=f'正在拼接 {completed_count} 个镜头视频...')
            merged_file = merge_videos(drama_id, video_results)
            if merged_file:
                _update(merged_video=merged_file, message=f'短剧生成完成！{completed_count}/{len(shots)} 个镜头成功，已合并为完整视频')
            else:
                _update(message=f'短剧生成完成！{completed_count}/{len(shots)} 个镜头成功（拼接失败，可单独查看）')
        else:
            _update(message=f'短剧生成完成！{completed_count}/{len(shots)} 个镜头成功')
        _update(status='completed')
        print(f"[短剧 {drama_id}] 完成: {video_results}")

    except Exception as e:
        print(f"[短剧 {drama_id}] 流水线异常: {e}")
        _update(status='failed', message=f'流水线错误: {e}')


# ==================== 短剧 API 路由 ====================

@drama_bp.route('/api/drama/start', methods=['POST'])
def drama_start():
    """启动短剧生成流水线"""
    data = request.get_json()
    api_key = get_api_key()
    if not api_key:
        return jsonify({'success': False, 'error': '请先配置 API Key'}), 401

    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'success': False, 'error': '请输入短剧描述'}), 400

    shot_duration = data.get('shot_duration', 5)
    text_model = data.get('text_model', DEFAULT_TEXT_MODEL)
    image_model = data.get('image_model', DEFAULT_IMAGE_MODEL)
    video_model = data.get('video_model', DEFAULT_VIDEO_MODEL)
    drama_id = uuid.uuid4().hex[:12]

    text_api_key = get_vendor_api_key(text_model, fallback_key=api_key)

    with drama_lock:
        drama_tasks[drama_id] = {
            'drama_id': drama_id, 'status': 'pending', 'step': '',
            'prompt': prompt, 'shot_duration': shot_duration,
            'text_model': text_model, 'image_model': image_model, 'video_model': video_model,
            'text_api_key': text_api_key,
            'script': None, 'storyboard': None, 'shots': [],
            'assets': [], 'video_results': [],
            'message': '正在启动...', 'created_at': time.time()
        }

    thread = threading.Thread(target=drama_pipeline, args=(drama_id, api_key, text_api_key), daemon=True)
    thread.start()

    return jsonify({'success': True, 'drama_id': drama_id, 'status': 'pending'})


@drama_bp.route('/api/drama/models', methods=['GET'])
def drama_models():
    """返回可选模型列表"""
    return jsonify({
        'success': True,
        'text_models': TEXT_MODEL_OPTIONS,
        'image_models': IMAGE_MODEL_OPTIONS,
        'video_models': VIDEO_MODEL_OPTIONS,
        'defaults': {
            'text_model': DEFAULT_TEXT_MODEL,
            'image_model': DEFAULT_IMAGE_MODEL,
            'video_model': DEFAULT_VIDEO_MODEL
        }
    })


@drama_bp.route('/api/drama/status/<drama_id>', methods=['GET'])
def drama_status(drama_id):
    """查询短剧任务状态"""
    with drama_lock:
        drama = drama_tasks.get(drama_id)
        if not drama:
            return jsonify({'success': False, 'error': '任务不存在'}), 404
        return jsonify({
            'success': True,
            'drama_id': drama['drama_id'],
            'status': drama['status'],
            'step': drama.get('step', ''),
            'message': drama.get('message', ''),
            'prompt': drama['prompt'],
            'shot_duration': drama.get('shot_duration', 5),
            'script': drama.get('script'),
            'storyboard': drama.get('storyboard'),
            'assets': drama.get('assets', []),
            'video_results': drama.get('video_results', []),
            'merged_video': drama.get('merged_video'),
            'shots_count': len(drama.get('shots', [])),
            'completed_shots': sum(1 for v in drama.get('video_results', []) if v.get('status') == 'completed'),
            'created_at': drama['created_at']
        })


@drama_bp.route('/api/drama/list', methods=['GET'])
def drama_list():
    """列出所有短剧任务"""
    with drama_lock:
        items = []
        for did, d in drama_tasks.items():
            items.append({
                'drama_id': d['drama_id'], 'status': d['status'],
                'prompt': d['prompt'][:60] + ('...' if len(d['prompt']) > 60 else ''),
                'shot_duration': d.get('shot_duration', 5),
                'shots_count': len(d.get('shots', [])),
                'completed_shots': sum(1 for v in d.get('video_results', []) if v.get('status') == 'completed'),
                'assets_count': len(d.get('assets', [])),
                'message': d.get('message', ''),
                'created_at': d['created_at']
            })
        return jsonify({'success': True, 'dramas': items})
