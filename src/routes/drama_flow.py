"""
短剧节点流（ComfyUI 式画布）路由 + 图执行引擎

节点类型: prompt → story → script → storyboard → assets → shots → merge
每个节点是一次独立任务，状态/输出落盘 dramas/flows/<flow_id>.json，
支持整图运行、单节点重跑、下游级联重跑、手动编辑节点输出。
"""

import os
import re
import json
import time
import uuid
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, jsonify

from ..config import get_api_key, get_app_dir, get_vendor_api_key, get_vendor_base_url, shutdown_event
from ..models import ensure_drama_dirs, DEFAULT_TEXT_MODEL, DEFAULT_IMAGE_MODEL, DEFAULT_VIDEO_MODEL
from ..services.text_model import (
    call_text_model, parse_json_from_text,
    story_system_prompt, script_system_prompt, storyboard_system_prompt, assets_system_prompt,
    review_system_prompt,
    build_video_prompt, sanitize_image_prompt, translate_cn_to_en, is_mostly_chinese,
)
from ..services.gemini_image import is_gemini_image, generate_gemini_image
from ..services.video_gen import (download_and_save_file, run_video_job, query_video_task,
                                  download_generated_video, extract_video_url)
from ..services.video_merge import merge_videos, burn_chinese_subtitle
from .drama import build_character_image_prompt, get_style_base, DEFAULT_CHARACTER_STYLE

flow_bp = Blueprint('drama_flow', __name__)

# ---------- 存储 ----------

flows = {}                       # flow_id -> flow dict
flow_lock = threading.Lock()
flow_stop_events = {}            # flow_id -> threading.Event
flow_running = set()             # flow_id 正在执行整图/下游任务（防重复点击启动并发线程互相覆盖节点状态）
# 镜头级 override 与云端在途任务存于 flow['shot_overrides'] / flow['inflight']，
# 随 flow JSON 原子落盘，重启由 recover_inflight_shots 回收

# 节点上游依赖类型（找最近的祖先节点输出）
UPSTREAM = {
    'story': ['prompt'],
    'script': ['story', 'prompt'],
    'storyboard': ['script', 'story'],
    'assets': ['script', 'storyboard'],
    'shots': ['storyboard', 'assets'],
    'merge': ['shots'],
}

NODE_LABELS = {
    'prompt': '✏️ 描述', 'story': '📖 故事', 'script': '📝 剧本',
    'storyboard': '🎬 分镜', 'assets': '🖼 素材', 'shots': '🎥 镜头视频', 'merge': '🧩 合并',
}

DEFAULT_LINEAR = ['prompt', 'story', 'script', 'storyboard', 'assets', 'shots', 'merge']


def _flows_dir():
    d = os.path.join(get_app_dir(), 'dramas', 'flows')
    os.makedirs(d, exist_ok=True)
    return d


def _templates_dir():
    d = os.path.join(get_app_dir(), 'dramas', 'flow_templates')
    os.makedirs(d, exist_ok=True)
    return d


def _persist(flow_id):
    """落盘（调用方需持有或不需要锁，写文件本身原子替换）"""
    with flow_lock:
        flow = flows.get(flow_id)
        if not flow:
            return
        snapshot = json.dumps(flow, ensure_ascii=False, indent=1, default=str)
    path = os.path.join(_flows_dir(), f'{flow_id}.json')
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(snapshot)
    os.replace(tmp, path)


def _load_flow(flow_id):
    """内存优先，其次磁盘（重启恢复）"""
    with flow_lock:
        if flow_id in flows:
            return flows[flow_id]
    path = os.path.join(_flows_dir(), f'{flow_id}.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            flow = json.load(f)
        # 重启后 running 节点视为中断；无在途云端任务的 generating 镜头标记失败
        inflight_keys = {str(e.get('shot_index')) for e in (flow.get('inflight') or {}).values()}
        for n in flow.get('nodes', {}).values():
            if n.get('status') == 'running':
                n['status'] = 'interrupted'
            if n.get('type') == 'shots':
                for r in ((n.get('output') or {}).get('results') or []):
                    if r.get('status') == 'generating' and str(r.get('shot_index')) not in inflight_keys:
                        r['status'] = 'failed'
                        r['error'] = '服务重启中断'
        with flow_lock:
            flows[flow_id] = flow
        return flow
    except Exception:
        return None


def default_graph():
    """默认线性图（自动布局坐标）"""
    nodes, edges = {}, []
    prev = None
    for i, t in enumerate(DEFAULT_LINEAR):
        nid = f'n{i+1}'
        nodes[nid] = {'id': nid, 'type': t, 'status': 'pending', 'output': None,
                      'error': '', 'updated_at': 0,
                      'pos': {'x': 60 + i * 300, 'y': 120 if t not in ('assets', 'shots') else 340}}
        if prev:
            edges.append({'id': f'e{prev}-{nid}', 'source': prev, 'target': nid})
        prev = nid
    return nodes, edges


# ---------- 图工具 ----------

def _downstream_ids(nodes, edges, node_id):
    """BFS 下游节点 id（不含自身）"""
    adj = {}
    for e in edges:
        adj.setdefault(e['source'], []).append(e['target'])
    seen, queue = set(), [node_id]
    while queue:
        cur = queue.pop()
        for nxt in adj.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return list(seen)


def _topo_order(nodes, edges, only_ids=None):
    """拓扑排序，only_ids 限定子集"""
    ids = set(only_ids) if only_ids is not None else set(nodes.keys())
    indeg = {i: 0 for i in ids}
    adj = {}
    for e in edges:
        if e['source'] in ids and e['target'] in ids:
            adj.setdefault(e['source'], []).append(e['target'])
            indeg[e['target']] += 1
    queue = [i for i in ids if indeg[i] == 0]
    order = []
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for nxt in adj.get(cur, []):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(ids):
        return None  # 有环
    return order


def _upstream_outputs(flow, node_id, needed_types):
    """BFS 向上找每种所需类型的最近祖先输出"""
    parents = {}
    for e in flow['edges']:
        parents.setdefault(e['target'], []).append(e['source'])
    found, visited, queue = {}, set(), list(parents.get(node_id, []))
    want = set(needed_types)
    while queue and want:
        cur = queue.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        node = flow['nodes'].get(cur)
        if node and node['type'] in want and node.get('output') is not None:
            found[node['type']] = node['output']
            want.discard(node['type'])
        queue.extend(parents.get(cur, []))
    return found


def _set_node(flow_id, node_id, **kw):
    with flow_lock:
        flow = flows.get(flow_id)
        if flow and node_id in flow['nodes']:
            flow['nodes'][node_id].update(kw)
            flow['nodes'][node_id]['updated_at'] = time.time()
    _persist(flow_id)


def _mark_stale(flow_id, node_id):
    """节点重跑后，下游标记为 stale"""
    with flow_lock:
        flow = flows.get(flow_id)
        if not flow:
            return
        for did in _downstream_ids(flow['nodes'], flow['edges'], node_id):
            n = flow['nodes'].get(did)
            if n and n['status'] in ('completed', 'partial'):
                n['status'] = 'stale'
    _persist(flow_id)


# ---------- 节点执行器 ----------

def _resolve_api_key(flow):
    return get_api_key()


def _aborted(flow_id):
    return flow_stop_events.get(flow_id, threading.Event()).is_set() or shutdown_event.is_set()


def _node_params(flow, node):
    """节点级参数覆盖：默认继承流参数，node['params'] 中的键优先（ComfyUI 式每节点独立配置）"""
    return {**flow['params'], **(node.get('params') or {})}


# ---------- 输入签名缓存（借鉴 comfy_execution/caching.py） ----------
# sig = hash(节点类型 + 节点级覆盖参数 + 每个父节点的[输出哈希, 父sig])，递归到根。
# 上游重跑但输出不变 → 下游 sig 命中 → 跳过执行（不重复烧钱）；
# 输出变了 / 节点参数覆盖了 / 手动编辑了输出 → sig 失配 → 自动重跑。
# 全局 flow.params 变化不参与 sig（与旧行为一致：completed 节点不因此重跑）。

def _out_hash(node):
    o = node.get('output')
    if o is None:
        return None
    return hashlib.sha1(json.dumps(o, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def _node_sig(flow, node_id):
    node = flow['nodes'][node_id]
    parents = sorted(e['source'] for e in flow['edges'] if e['target'] == node_id)
    parts = [node['type'], node.get('params') or {}]
    for p in parents:
        pn = flow['nodes'].get(p)
        if pn:
            parts.append((p, _out_hash(pn), _node_sig(flow, p)))
    return hashlib.sha1(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def _cache_hit(flow, node_id):
    """已完成且 sig 一致 → 跳过。旧数据无 sig 字段：信任其 completed 状态并回填，避免升级后全图重跑"""
    node = flow['nodes'].get(node_id)
    if not node or node.get('status') != 'completed':
        return False
    if node.get('sig') is None:
        node['sig'] = _node_sig(flow, node_id)
        return True
    return node['sig'] == _node_sig(flow, node_id)


# ---------- 确定性时长引擎（借鉴 shuohao novel-script：台词 4.5 字/秒、动作节拍 2.5 秒） ----------
CHARS_PER_SEC = 4.5
ACTION_SECONDS = 2.5
DUR_TIERS = [5, 10, 18]
DUR_TOLERANCE = 1.15   # ±15%


def _shot_est_seconds(shot):
    dlg = re.sub(r'\s+', '', shot.get('dialogue') or '')
    return len(dlg) / CHARS_PER_SEC + ACTION_SECONDS


def _fit_shot_duration(shot, base_dur):
    """台词装不下就自动升档（5→10→18），短台词保持基础档——不升档字幕与画面必然脱节"""
    est = _shot_est_seconds(shot)
    dur = base_dur
    while est > dur * DUR_TOLERANCE:
        nxt = next((t for t in DUR_TIERS if t > dur), None)
        if nxt is None:
            break
        dur = nxt
    return dur


def _validate_shots(shots, base_dur):
    """分镜产出后的确定性校验：返回 (逐镜升档警告, 无法救回的超限错误)"""
    warnings, over = [], []
    for s in shots:
        est = _shot_est_seconds(s)
        si = s.get('shot_index')
        if est > DUR_TIERS[-1] * DUR_TOLERANCE:
            over.append(f'镜头{si}台词约 {est:.0f} 秒，超过最长 {DUR_TIERS[-1]} 秒档容量，请拆分台词后重跑分镜')
        elif est > base_dur * DUR_TOLERANCE:
            fit = _fit_shot_duration(s, base_dur)
            warnings.append(f'镜头{si}台词约 {est:.0f} 秒，生成时将自动用 {fit} 秒档')
    return warnings, over


def _crosscheck_refs(shots, assets):
    """分镜引用的角色必须能在资产清单里找到（借鉴 refs-scenes 门）：
    不匹配时 _match_assets 会静默回退第一个角色——视频换脸了没人知道，这里显式报出来"""
    names = [a.get('name', '').lower().strip() for a in assets if a.get('name')]
    warnings = []
    for s in shots:
        for c in s.get('characters', []):
            cl = c.lower().strip()
            if cl and not any(cl in n or n in cl for n in names):
                warnings.append({'shot_index': s.get('shot_index'), 'kind': '角色', 'name': c})
    return warnings


def _run_prompt_node(flow, node):
    p = flow['params'].get('prompt', '').strip()
    if not p:
        raise ValueError('缺少短剧描述')
    return {'prompt': p}


def _run_story_node(flow, node):
    up = _upstream_outputs(flow, node['id'], UPSTREAM['story'])
    src = up.get('prompt', {}).get('prompt', '')
    api_key = _resolve_api_key(flow)
    text_model = _node_params(flow, node).get('text_model', DEFAULT_TEXT_MODEL)
    key = get_vendor_api_key(text_model, fallback_key=api_key)
    text = call_text_model(story_system_prompt(),
                           f"请根据以下描述，创作一个 300～500 字的短剧故事：\n{src}",
                           key, model=text_model, abort_check=lambda: _aborted(flow['flow_id']))
    return {'text': text}


def _run_script_node(flow, node):
    up = _upstream_outputs(flow, node['id'], UPSTREAM['script'])
    story = up.get('story', {}).get('text', '') or up.get('prompt', {}).get('prompt', '')
    api_key = _resolve_api_key(flow)
    text_model = _node_params(flow, node).get('text_model', DEFAULT_TEXT_MODEL)
    key = get_vendor_api_key(text_model, fallback_key=api_key)
    text = call_text_model(script_system_prompt(),
                           f"请将以下故事 1:1 精准还原为专业短剧剧本，要求画面描述详细，有 vo 的台词必须搭配画面，特写镜头要标注：\n\n{story}",
                           key, model=text_model, max_tokens=8192, abort_check=lambda: _aborted(flow['flow_id']))
    return {'text': text}


def _review_shots(shots, key, text_model, flow_id):
    """LLM 自审修复：按视频模型能力边界清单改一遍分镜（一次便宜调用，省下游贵的生成）。
    解析失败或镜头数偏差 >30% 时保留原稿，绝不让审校毁掉产出"""
    try:
        rv = call_text_model(review_system_prompt(),
                             json.dumps({'shots': shots}, ensure_ascii=False),
                             key, model=text_model, max_tokens=16384, temperature=0.3,
                             abort_check=lambda: _aborted(flow_id))
        revised = (parse_json_from_text(rv) or {}).get('shots') or []
        if revised and abs(len(revised) - len(shots)) <= max(2, len(shots) * 0.3):
            print(f'[短剧流] 分镜自审修复：{len(shots)} → {len(revised)} 个镜头')
            return revised
        print('[短剧流] 分镜自审结果偏差过大，保留原稿')
    except Exception as e:
        if _aborted(flow_id) or '已中止' in str(e):
            raise
        print(f'[短剧流] 分镜自审跳过（{type(e).__name__}: {str(e)[:100]}）')
    return shots


def _run_storyboard_node(flow, node):
    up = _upstream_outputs(flow, node['id'], UPSTREAM['storyboard'])
    script = up.get('script', {}).get('text', '') or up.get('story', {}).get('text', '')
    params = _node_params(flow, node)
    shot_dur = params.get('shot_duration', 5)
    api_key = _resolve_api_key(flow)
    text_model = params.get('text_model', DEFAULT_TEXT_MODEL)
    key = get_vendor_api_key(text_model, fallback_key=api_key)
    sb_text = call_text_model(storyboard_system_prompt(shot_dur),
                              f"请将以下剧本改写为分镜脚本，每个分镜约{shot_dur}秒：\n\n{script}",
                              key, model=text_model, max_tokens=16384, temperature=0.4,
                              abort_check=lambda: _aborted(flow['flow_id']))
    sb = parse_json_from_text(sb_text)
    shots = sb.get('shots', [])
    if not shots:
        raise ValueError('分镜解析失败：未得到 shots')
    shots = _review_shots(shots, key, text_model, flow['flow_id'])
    warnings, over = _validate_shots(shots, shot_dur)
    if over:
        raise ValueError('；'.join(over[:5]))
    return {'shots': shots, 'warnings': warnings}


def _match_assets(shot, assets):
    """按角色/场景/道具名匹配镜头素材（与旧流水线逻辑一致）"""
    matched, primary = [], None
    shot_chars = [c.lower().strip() for c in shot.get('characters', [])]
    scene_desc = shot.get('scene_desc', '').lower()
    action = shot.get('action', '').lower()
    for a in assets:
        if not a.get('image_url'):
            continue
        name = a.get('name', '').lower().strip()
        if not name:
            continue
        cat = a.get('category')
        hit = (cat == 'characters' and any(name in c or c in name for c in shot_chars)) \
            or (cat == 'scenes' and name in scene_desc) \
            or (cat == 'props' and name in action)
        if hit:
            matched.append(a)
            if not primary:
                primary = a['image_url']
    if not primary:
        for a in assets:
            if a.get('image_url') and a.get('category') == 'characters':
                primary = a['image_url']
                if a not in matched:
                    matched.append(a)
                break
    return matched, primary


def _generate_asset_image(flow, asset, idx, drama_id, params=None):
    """生成单个素材参考图，返回 (image_url, local_file, img_prompt)"""
    params = params or flow['params']
    category = asset.get('category', 'characters')
    desc = asset.get('desc', '')
    style = params.get('character_style', DEFAULT_CHARACTER_STYLE)
    prompt_en = asset.get('prompt_en', '')
    if prompt_en:
        img_prompt = prompt_en
        img_size = '1344x768' if category == 'scenes' else '768x1344'
    elif category == 'characters':
        img_prompt, img_size = build_character_image_prompt(desc, style)
    elif category == 'scenes':
        img_prompt = (f"{get_style_base('scene', style)}"
                      f"16:9 horizontal composition, pure white background border. "
                      f"Scene environment design concept art, multiple angles view. "
                      f"Scene description: {desc}. Highly detailed environment, consistent style. "
                      f"Absolutely no people anywhere. THE SPACE MUST BE IDENTICAL ACROSS ALL PANELS.")
        img_size = '1344x768'
    else:
        img_prompt = (f"{get_style_base('prop', style)}"
                      f"9:16 vertical composition, pure white minimalist background, premium prop design board layout. "
                      f"Multiple views: front, side, back, top, detail close-ups. "
                      f"Material and texture details clearly visible. Prop description: {desc}. "
                      f"Consistent design, no deformation. Pure white background, no people, no hands anywhere in frame, "
                      f"clear real-world scale reference.")
        img_size = '768x1344'
    img_prompt = sanitize_image_prompt(img_prompt)
    image_model = params.get('image_model', DEFAULT_IMAGE_MODEL)
    api_key = _resolve_api_key(flow)
    safe_name = (asset.get('name') or f'asset_{idx}').replace(' ', '_')
    img_api_key = get_vendor_api_key(image_model, fallback_key=api_key)
    img_base_url = get_vendor_base_url(image_model)
    import requests
    headers = {'Authorization': f'Bearer {img_api_key}', 'Content-Type': 'application/json'}
    last_err = '未知错误'
    for attempt in range(3):
        try:
            if is_gemini_image(image_model):
                from ..config import get_custom_model_config
                if not get_custom_model_config(image_model):
                    url, local = generate_gemini_image(img_prompt, image_model,
                                                       f'dramas/{drama_id}/images', safe_name)
                    return url, local, img_prompt
            resp = requests.post(f'{img_base_url}/images/generations', headers=headers,
                                 json={'model': image_model, 'prompt': img_prompt, 'size': img_size},
                                 timeout=180)
            if resp.status_code == 200:
                result = resp.json()
                data = result.get('data') or []
                if data and data[0].get('url'):
                    image_url = data[0]['url']
                    local = download_and_save_file(image_url, f'dramas/{drama_id}/images', safe_name, 'png')
                    return image_url, local, img_prompt
                last_err = f'响应无 url: {json.dumps(result, ensure_ascii=False)[:200]}'
            elif resp.status_code in (429, 503, 433):
                last_err = f'限流 {resp.status_code}'
                for _ in range(15 * (attempt + 1)):
                    if _aborted(flow['flow_id']):
                        raise RuntimeError('已中止')
                    time.sleep(1)
                continue
            else:
                last_err = f'API {resp.status_code}: {resp.text[:200]}'
        except RuntimeError:
            raise
        except Exception as e:
            last_err = f'{type(e).__name__}: {e}'
        if _aborted(flow['flow_id']):
            raise RuntimeError('已中止')
        time.sleep(3)
    raise RuntimeError(f'素材 [{asset.get("name", idx)}] 生图失败: {last_err}')


def _run_assets_node(flow, node):
    drama_id = flow['drama_id']
    up = _upstream_outputs(flow, node['id'], UPSTREAM['assets'])
    script = up.get('script', {}).get('text', '')
    sb = up.get('storyboard', {}).get('shots', [])
    api_key = _resolve_api_key(flow)
    params = _node_params(flow, node)
    text_model = params.get('text_model', DEFAULT_TEXT_MODEL)
    key = get_vendor_api_key(text_model, fallback_key=api_key)
    assets_text = call_text_model(assets_system_prompt(),
                                  f"请从以下剧本和分镜中提取所有角色、场景、道具的视觉特征描述：\n"
                                  f"剧本：\n{script}\n\n分镜：\n{json.dumps(sb, ensure_ascii=False)}",
                                  key, model=text_model, max_tokens=16384,
                                  abort_check=lambda: _aborted(flow['flow_id']))
    raw = parse_json_from_text(assets_text)
    all_assets = []
    for cat in ('characters', 'scenes', 'props'):
        for item in raw.get(cat, []):
            all_assets.append({'category': cat, 'name': item.get('name', ''),
                               'desc': item.get('desc', ''), 'prompt_en': item.get('prompt_en', ''),
                               'image_url': None, 'local_file': None, 'img_prompt': ''})
    if not all_assets:
        raise ValueError('素材提取结果为空')
    ensure_drama_dirs(drama_id)
    ok = 0
    failed = []
    for idx, asset in enumerate(all_assets):
        if flow_stop_events.get(flow['flow_id'], threading.Event()).is_set() or shutdown_event.is_set():
            raise RuntimeError('已中止')
        _set_node(flow['flow_id'], node['id'], status='running', error='')  # 下载中保持 running，前端显示 loading
        try:
            url, local, img_prompt = _generate_asset_image(flow, asset, idx, drama_id, params)
            asset['image_url'], asset['local_file'], asset['img_prompt'] = url, local, img_prompt
            ok += 1
        except Exception as e:
            asset['error'] = str(e)[:200]
            failed.append(asset['name'] or f'#{idx}')
        if idx < len(all_assets) - 1:
            time.sleep(2)
        with flow_lock:
            flow['nodes'][node['id']]['output'] = {'assets': all_assets, 'progress': f'{ok + len(failed)}/{len(all_assets)}'}
    if ok == 0:
        raise RuntimeError(f'全部 {len(all_assets)} 个素材生图失败')
    ref_warnings = _crosscheck_refs(sb, all_assets)
    if ref_warnings:
        print(f'[短剧流 {flow["flow_id"]}] 素材对账：{len(ref_warnings)} 个分镜角色在资产清单中找不到，镜头生成将回退默认角色参考')
    return {'assets': all_assets, 'failed': failed, 'ref_warnings': ref_warnings}


def _run_shot_video(flow, shot, drama_id, params=None):
    """生成单镜头视频（含字幕烧录），返回结果 dict"""
    shot_index = shot.get('shot_index')
    params = params or flow['params']
    all_assets = flow['_shot_assets_cache']
    override = (flow.get('shot_overrides') or {}).get(str(shot_index)) or {}
    shot_dur = _fit_shot_duration(shot, params.get('shot_duration', 5))
    num_frames = {5: 121, 10: 241, 18: 441}.get(shot_dur, 121)
    flow_id = flow['flow_id']
    abort = lambda: flow_stop_events.get(flow_id, threading.Event()).is_set() or shutdown_event.is_set()

    custom_prompt = override.get('custom_prompt', '')
    prompt_cn = ''
    if custom_prompt:
        if is_mostly_chinese(custom_prompt):
            api_key = _resolve_api_key(flow)
            text_model = params.get('text_model', DEFAULT_TEXT_MODEL)
            prompt = translate_cn_to_en(custom_prompt, get_vendor_api_key(text_model, fallback_key=api_key), text_model)
            prompt_cn = custom_prompt
        else:
            prompt = prompt_cn = custom_prompt
    else:
        matched, _ = _match_assets(shot, all_assets)
        prompt, prompt_cn = build_video_prompt(shot, matched)

    custom_images = override.get('custom_images')
    if custom_images:
        primary = custom_images[0].get('image_url', '')
        extra = [i.get('image_url') for i in custom_images[1:] if i.get('image_url')]
    else:
        matched, primary = _match_assets(shot, all_assets)
        extra = []

    video_model = params.get('video_model', DEFAULT_VIDEO_MODEL)
    save_subdir = f'dramas/{drama_id}/videos'

    def _on_submit(ids):
        """提交成功即落盘 inflight，服务重启后可回收云端已付费的生成结果"""
        with flow_lock:
            flow.setdefault('inflight', {})[str(shot_index)] = {
                **ids, 'shot_index': shot_index, 'prompt': prompt, 'prompt_cn': prompt_cn,
                'primary_image': primary, 'video_model': video_model,
                'save_subdir': save_subdir, 'saved_at': time.time()}
        _persist(flow_id)

    res = run_video_job(
        video_model, prompt,
        primary_image=primary, extra_images=extra, num_frames=num_frames,
        api_key=_resolve_api_key(flow),
        negative_prompt='text, subtitles, captions, labels, letters, words, watermark, any text overlay',
        width=768, height=1152, save_subdir=save_subdir,
        prefix=f'shot_{shot_index}', abort_check=abort, on_submit=_on_submit)

    # 任务结束（成功/失败/中止）清 inflight；服务关闭时保留，交由重启回收
    if not shutdown_event.is_set():
        with flow_lock:
            flow.get('inflight', {}).pop(str(shot_index), None)
        _persist(flow_id)

    if res['ok'] and shot.get('dialogue'):
        try:
            full = os.path.join(get_app_dir(), save_subdir, res['local_file'])
            if os.path.exists(full):
                burn_chinese_subtitle(full, shot['dialogue'])
        except Exception as e:
            print(f'[flow] 镜头{shot_index} 字幕烧录异常: {e}')

    return {'shot_index': shot_index, 'status': 'completed' if res['ok'] else 'failed',
            'local_file': res['local_file'], 'video_url': res['video_url'],
            'error': res['error'], 'prompt': prompt, 'prompt_cn': prompt_cn,
            'primary_image': primary}


def _reuse_completed_shots(flow, node, shots, drama_id):
    """已有 completed 且本地文件存在的镜头结果 → 直接复用，重跑不重复烧钱"""
    videos_dir = os.path.join(get_app_dir(), 'dramas', drama_id, 'videos')
    reused = {}
    for r in ((node.get('output') or {}).get('results') or []):
        si = r.get('shot_index')
        if (r.get('status') == 'completed' and r.get('local_file')
                and os.path.exists(os.path.join(videos_dir, r['local_file']))):
            reused[si] = r
    return reused


def _run_shots_node(flow, node):
    drama_id = flow['drama_id']
    up = _upstream_outputs(flow, node['id'], UPSTREAM['shots'])
    shots = up.get('storyboard', {}).get('shots', [])
    assets = up.get('assets', {}).get('assets', [])
    if not shots:
        raise ValueError('缺少分镜输出')
    ensure_drama_dirs(drama_id)
    flow['_shot_assets_cache'] = assets

    results = dict(_reuse_completed_shots(flow, node, shots, drama_id))
    todo_shots = [s for s in shots if s.get('shot_index') not in results]
    if results:
        print(f'[短剧流 {flow["flow_id"]}] 复用 {len(results)} 个已完成镜头，跳过生成')
    lock = threading.Lock()

    def _update_output():
        with lock:
            snapshot = list(results.values())
        with flow_lock:
            flow['nodes'][node['id']]['output'] = {'results': snapshot}

    _update_output()
    params = _node_params(flow, node)
    max_workers = int(params.get('shot_workers', 2))
    aborted = flow_stop_events.get(flow['flow_id'], threading.Event())
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(_run_shot_video, flow, s, drama_id, params): s for s in todo_shots}
        for fut, shot in futs.items():
            si = shot.get('shot_index')
            try:
                r = fut.result()
            except Exception as e:
                r = {'shot_index': si, 'status': 'failed', 'error': str(e)[:200]}
            results[si] = r
            _update_output()
            if aborted.is_set():
                for f2 in futs.values():
                    f2.cancel()
    ordered = [results[s.get('shot_index')] for s in shots if s.get('shot_index') in results]
    if aborted.is_set() and any(r['status'] == 'failed' and r.get('error') == '已中止' for r in ordered):
        raise RuntimeError('已中止')
    if not any(r['status'] == 'completed' for r in ordered):
        raise RuntimeError('全部镜头生成失败')
    return {'results': ordered}


def _run_merge_node(flow, node):
    drama_id = flow['drama_id']
    up = _upstream_outputs(flow, node['id'], UPSTREAM['merge'])
    results = up.get('shots', {}).get('results', [])
    order = _node_params(flow, node).get('merge_order') or None
    merged = merge_videos(drama_id, results, shot_order=order, output_prefix='flow_merged')
    if not merged:
        raise RuntimeError('合并失败：成功视频不足 2 个或 ffmpeg 不可用')
    with flow_lock:
        flow['merged_video'] = merged
    return {'merged_file': merged}


NODE_RUNNERS = {
    'prompt': _run_prompt_node, 'story': _run_story_node, 'script': _run_script_node,
    'storyboard': _run_storyboard_node, 'assets': _run_assets_node,
    'shots': _run_shots_node, 'merge': _run_merge_node,
}


def _execute_node(flow_id, node_id):
    """执行单节点：running → completed/failed；输入签名命中则跳过。返回 True=成功"""
    _set_node(flow_id, node_id, status='running', error='')
    with flow_lock:
        flow = flows.get(flow_id)
        node = flow['nodes'][node_id] if flow else None
    if not node:
        return False
    if _cache_hit(flow, node_id):
        _set_node(flow_id, node_id, status='completed')
        _persist(flow_id)
        print(f'[短剧流 {flow_id}] 节点 {node["type"]}({node_id}) 输入未变，缓存命中跳过')
        return True
    try:
        runner = NODE_RUNNERS.get(node['type'])
        if not runner:
            raise ValueError(f'未知节点类型: {node["type"]}')
        output = runner(flow, node)
        with flow_lock:
            sig = _node_sig(flows[flow_id], node_id)
        _set_node(flow_id, node_id, status='completed', output=output, error='', sig=sig)
        _mark_stale(flow_id, node_id)
        print(f'[短剧流 {flow_id}] 节点 {node["type"]}({node_id}) 完成')
        return True
    except Exception as e:
        _set_node(flow_id, node_id, status='failed', error=str(e)[:500])
        print(f'[短剧流 {flow_id}] 节点 {node.get("type")}({node_id}) 失败: {e}')
        return False


def _upstream_pending(flow, node_id):
    """ComfyUI 式 run-from-node：沿边收集所有未完成的祖先，先补齐再跑目标节点"""
    parents = {}
    for e in flow['edges']:
        parents.setdefault(e['target'], []).append(e['source'])
    need, visited, queue = [], set(), list(parents.get(node_id, []))
    while queue:
        cur = queue.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        n = flow['nodes'].get(cur)
        if n and not _cache_hit(flow, cur):
            need.append(cur)
        queue.extend(parents.get(cur, []))
    return need + [node_id]


def _run_graph(flow_id, node_ids):
    """按拓扑序执行给定节点子集，任一失败即停"""
    try:
        with flow_lock:
            flow = flows.get(flow_id)
            if not flow:
                return
            order = _topo_order(flow['nodes'], flow['edges'], node_ids)
        if order is None:
            _set_node(flow_id, node_ids[0] if node_ids else '', status='failed', error='图中存在环路')
            return
        for nid in order:
            if flow_stop_events.get(flow_id, threading.Event()).is_set() or shutdown_event.is_set():
                with flow_lock:
                    f = flows.get(flow_id)
                    if f:
                        for n in f['nodes'].values():
                            if n['status'] in ('pending', 'running'):
                                n['status'] = 'stopped'
                _persist(flow_id)
                return
            ok = _execute_node(flow_id, nid)
            if not ok:
                return
    finally:
        with flow_lock:
            flow_running.discard(flow_id)


# ==================== API ====================

@flow_bp.route('/api/drama/flow/create', methods=['POST'])
def flow_create():
    data = request.get_json(silent=True) or {}
    params = {
        'prompt': data.get('prompt', ''),
        'shot_duration': data.get('shot_duration', 5),
        'text_model': data.get('text_model', DEFAULT_TEXT_MODEL),
        'image_model': data.get('image_model', DEFAULT_IMAGE_MODEL),
        'video_model': data.get('video_model', DEFAULT_VIDEO_MODEL),
        'character_style': data.get('character_style', DEFAULT_CHARACTER_STYLE),
        'shot_workers': data.get('shot_workers', 2),
        'merge_order': data.get('merge_order'),
    }
    nodes, edges = default_graph()
    # 从模板创建时覆盖图结构
    if data.get('template'):
        tpl = os.path.join(_templates_dir(), f'{data["template"]}.json')
        if os.path.exists(tpl):
            with open(tpl, 'r', encoding='utf-8') as f:
                t = json.load(f)
            nodes, edges = t['nodes'], t['edges']

    flow_id = uuid.uuid4().hex[:12]
    flow = {
        'flow_id': flow_id, 'drama_id': flow_id,
        'name': data.get('name', params['prompt'][:30] or '未命名短剧流'),
        'params': params, 'nodes': nodes, 'edges': edges,
        'merged_video': None, 'created_at': time.time(),
    }
    with flow_lock:
        flows[flow_id] = flow
        flow_stop_events[flow_id] = threading.Event()
    _persist(flow_id)
    return jsonify({'success': True, 'flow_id': flow_id, 'flow': flow})


@flow_bp.route('/api/drama/flow/list', methods=['GET'])
def flow_list():
    items = []
    seen = set()
    for fn in sorted(os.listdir(_flows_dir()), key=lambda x: os.path.getmtime(os.path.join(_flows_dir(), x)), reverse=True):
        if not fn.endswith('.json'):
            continue
        fid = fn[:-5]
        flow = _load_flow(fid)
        if not flow:
            continue
        seen.add(fid)
        nodes = flow.get('nodes', {})
        items.append({
            'flow_id': fid, 'name': flow.get('name', ''),
            'prompt': flow.get('params', {}).get('prompt', '')[:50],
            'created_at': flow.get('created_at', 0),
            'merged_video': flow.get('merged_video'),
            'done': sum(1 for n in nodes.values() if n.get('status') == 'completed'),
            'total': len(nodes),
        })
    # 内存中未落盘新任务也在
    with flow_lock:
        for fid, flow in flows.items():
            if fid not in seen:
                items.append({'flow_id': fid, 'name': flow.get('name', ''),
                              'prompt': flow.get('params', {}).get('prompt', '')[:50],
                              'created_at': flow.get('created_at', 0),
                              'merged_video': flow.get('merged_video'),
                              'done': sum(1 for n in flow['nodes'].values() if n.get('status') == 'completed'),
                              'total': len(flow['nodes'])})
    return jsonify({'success': True, 'flows': items})


@flow_bp.route('/api/drama/flow/<flow_id>', methods=['GET'])
def flow_get(flow_id):
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    pub = {k: v for k, v in flow.items() if not k.startswith('_')}
    return jsonify({'success': True, 'flow': pub})


@flow_bp.route('/api/drama/flow/<flow_id>/graph', methods=['POST'])
def flow_save_graph(flow_id):
    """保存前端画布的节点位置/增删/连线"""
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    data = request.get_json(silent=True) or {}
    with flow_lock:
        if 'nodes' in data:
            merged = {}
            for n in data['nodes']:
                nid = n['id']
                old = flow['nodes'].get(nid)
                if old is None:
                    # 前端新增节点：补齐执行引擎依赖的默认字段
                    old = {'status': 'pending', 'output': None, 'error': '', 'updated_at': 0}
                old.update({'id': nid, 'type': n.get('type', old.get('type')),
                            'pos': n.get('pos', old.get('pos', {'x': 0, 'y': 0}))})
                merged[nid] = old
            flow['nodes'] = merged
        if 'edges' in data:
            flow['edges'] = data['edges']
        if 'params' in data:
            flow['params'].update(data['params'])
        if 'name' in data:
            flow['name'] = data['name']
    _persist(flow_id)
    return jsonify({'success': True})


@flow_bp.route('/api/drama/flow/<flow_id>/run', methods=['POST'])
def flow_run(flow_id):
    """整图运行（跳过已完成的节点）或运行指定节点"""
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    if not get_api_key():
        return jsonify({'success': False, 'error': '请先配置 API Key'}), 401
    data = request.get_json(silent=True) or {}
    node_id = data.get('node_id')
    force = data.get('force', False)

    if node_id:
        if node_id not in flow['nodes']:
            return jsonify({'success': False, 'error': '节点不存在'}), 404
        todo = _upstream_pending(flow, node_id)
    else:
        todo = [nid for nid in flow['nodes'] if force or not _cache_hit(flow, nid)]
    with flow_lock:
        if flow_id in flow_running:
            return jsonify({'success': False, 'error': '流程正在运行中，请等待完成'}), 409
        flow_running.add(flow_id)
    flow_stop_events[flow_id] = threading.Event()
    with flow_lock:
        for nid in todo:
            flow['nodes'][nid]['status'] = 'pending'
    _persist(flow_id)
    threading.Thread(target=_run_graph, args=(flow_id, todo), daemon=True).start()
    return jsonify({'success': True, 'queued': todo})


@flow_bp.route('/api/drama/flow/<flow_id>/run-downstream', methods=['POST'])
def flow_run_downstream(flow_id):
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    data = request.get_json(silent=True) or {}
    node_id = data.get('node_id')
    if node_id not in flow['nodes']:
        return jsonify({'success': False, 'error': '节点不存在'}), 404
    todo = [node_id] + _downstream_ids(flow['nodes'], flow['edges'], node_id)
    with flow_lock:
        if flow_id in flow_running:
            return jsonify({'success': False, 'error': '流程正在运行中，请等待完成'}), 409
        flow_running.add(flow_id)
    flow_stop_events[flow_id] = threading.Event()
    with flow_lock:
        for nid in todo:
            flow['nodes'][nid]['status'] = 'pending'
    _persist(flow_id)
    threading.Thread(target=_run_graph, args=(flow_id, todo), daemon=True).start()
    return jsonify({'success': True, 'queued': todo})


@flow_bp.route('/api/drama/flow/<flow_id>/stop', methods=['POST'])
def flow_stop(flow_id):
    flow_stop_events.setdefault(flow_id, threading.Event()).set()
    return jsonify({'success': True})


@flow_bp.route('/api/drama/flow/<flow_id>/node/<node_id>/params', methods=['POST'])
def flow_node_params(flow_id, node_id):
    """节点级参数覆盖（模型/时长/风格等），未覆盖的键继承 flow 参数"""
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    data = request.get_json(silent=True) or {}
    with flow_lock:
        node = flow['nodes'].get(node_id)
        if not node:
            return jsonify({'success': False, 'error': '节点不存在'}), 404
        params = data.get('params') or {}
        for k in ('shot_duration', 'shot_workers'):
            if k in params:
                params[k] = int(params[k])
        node['params'] = params
        node['updated_at'] = time.time()
    _persist(flow_id)
    return jsonify({'success': True})


@flow_bp.route('/api/drama/flow/<flow_id>/node/<node_id>/edit', methods=['POST'])
def flow_node_edit(flow_id, node_id):
    """手动编辑节点输出（故事/剧本文本、分镜 JSON、参数）"""
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    data = request.get_json(silent=True) or {}
    with flow_lock:
        node = flow['nodes'].get(node_id)
        if not node:
            return jsonify({'success': False, 'error': '节点不存在'}), 404
        if 'output' in data:
            node['output'] = data['output']
            node['status'] = 'completed'
            node['updated_at'] = time.time()
    _mark_stale(flow_id, node_id)
    _persist(flow_id)
    return jsonify({'success': True})


# ---------- 素材操作 ----------

def _assets_node_of(flow):
    for nid, n in flow['nodes'].items():
        if n['type'] == 'assets' and n.get('output'):
            return nid, n
    return None, None


@flow_bp.route('/api/drama/flow/<flow_id>/asset/replace', methods=['POST'])
def flow_asset_replace(flow_id):
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    nid, node = _assets_node_of(flow)
    if not node:
        return jsonify({'success': False, 'error': '素材节点无输出'}), 400
    try:
        idx = int(request.form.get('asset_index', ''))
    except ValueError:
        return jsonify({'success': False, 'error': '缺少 asset_index'}), 400
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '未上传文件'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'success': False, 'error': '文件名为空'}), 400
    base = ensure_drama_dirs(flow['drama_id'])
    ext = os.path.splitext(file.filename)[1].lower() or '.png'
    filename = f'asset_{idx}_custom{ext}'
    file.save(os.path.join(base, 'images', filename))
    with flow_lock:
        assets = node['output']['assets']
        if idx < 0 or idx >= len(assets):
            return jsonify({'success': False, 'error': '素材索引越界'}), 400
        assets[idx]['local_file'] = filename
        assets[idx]['image_url'] = f'/dramas/{flow["drama_id"]}/images/{filename}'
    _persist(flow_id)
    _mark_stale(flow_id, nid)
    return jsonify({'success': True, 'image_url': f'/dramas/{flow["drama_id"]}/images/{filename}'})


@flow_bp.route('/api/drama/flow/<flow_id>/asset/regenerate', methods=['POST'])
def flow_asset_regenerate(flow_id):
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    nid, node = _assets_node_of(flow)
    if not node:
        return jsonify({'success': False, 'error': '素材节点无输出'}), 400
    data = request.get_json(silent=True) or {}
    try:
        idx = int(data.get('asset_index'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': '缺少 asset_index'}), 400
    custom_desc = (data.get('custom_desc') or '').strip()
    with flow_lock:
        assets = node['output']['assets']
        if idx < 0 or idx >= len(assets):
            return jsonify({'success': False, 'error': '素材索引越界'}), 400
        asset = dict(assets[idx])
    if custom_desc:
        asset['desc'] = custom_desc
        asset['prompt_en'] = ''
    try:
        url, local, img_prompt = _generate_asset_image(flow, asset, idx, flow['drama_id'],
                                                        _node_params(flow, node))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    with flow_lock:
        assets[idx].update({'image_url': url, 'local_file': local, 'img_prompt': img_prompt,
                            'desc': asset['desc']})
        assets[idx].pop('error', None)
    _persist(flow_id)
    _mark_stale(flow_id, nid)
    return jsonify({'success': True, 'image_url': url, 'local_file': local, 'img_prompt': img_prompt})


# ---------- 镜头操作 ----------

def _shots_node_of(flow):
    # ponytail: 单镜头操作按类型路由到第一个有输出的 shots 节点；
    # 多个 shots 节点并行对比时需给 shot 端点传 node_id
    for nid, n in flow['nodes'].items():
        if n['type'] == 'shots':
            return nid, n
    return None, None


@flow_bp.route('/api/drama/flow/<flow_id>/shot/run', methods=['POST'])
def flow_shot_run(flow_id):
    """生成/重新生成单个镜头视频（后台线程）"""
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    data = request.get_json(silent=True) or {}
    try:
        shot_index = int(data.get('shot_index'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': '缺少 shot_index'}), 400
    sb_nid, sb_node = next(((i, n) for i, n in flow['nodes'].items()
                            if n['type'] == 'storyboard' and n.get('output')), (None, None))
    if not sb_node:
        return jsonify({'success': False, 'error': '分镜未生成'}), 400
    shots = sb_node['output']['shots']
    shot = next((s for s in shots if s.get('shot_index') == shot_index), None)
    if not shot:
        return jsonify({'success': False, 'error': f'镜头 {shot_index} 不存在'}), 404

    if data.get('custom_prompt') or data.get('custom_images'):
        with flow_lock:
            flow.setdefault('shot_overrides', {})[str(shot_index)] = {
                'custom_prompt': data.get('custom_prompt', ''),
                'custom_images': data.get('custom_images'),
            }
        _persist(flow_id)

    sh_nid, sh_node = _shots_node_of(flow)
    if not sh_node:
        # 自动创建 shots 节点输出容器
        sh_nid = next((i for i, n in flow['nodes'].items() if n['type'] == 'shots'), None)
        if not sh_nid:
            return jsonify({'success': False, 'error': '镜头节点不存在'}), 404
        with flow_lock:
            flow['nodes'][sh_nid]['output'] = {'results': []}
        sh_node = flow['nodes'][sh_nid]
    with flow_lock:
        results = sh_node.setdefault('output', {'results': []})['results']
        results[:] = [r for r in results if r.get('shot_index') != shot_index]
        results.append({'shot_index': shot_index, 'status': 'generating'})

    _, assets_node = _assets_node_of(flow)
    flow['_shot_assets_cache'] = assets_node['output']['assets'] if assets_node else []

    def _job():
        try:
            r = _run_shot_video(flow, shot, flow['drama_id'], _node_params(flow, sh_node))
        except Exception as e:
            r = {'shot_index': shot_index, 'status': 'failed', 'error': str(e)[:300]}
        with flow_lock:
            rs = sh_node['output']['results']
            rs[:] = [r2 for r2 in rs if r2.get('shot_index') != shot_index]
            rs.append(r)
        _persist(flow_id)
        print(f'[短剧流 {flow_id}] 镜头 {shot_index} -> {r["status"]}')
    threading.Thread(target=_job, daemon=True).start()
    return jsonify({'success': True, 'shot_index': shot_index})


@flow_bp.route('/api/drama/flow/<flow_id>/shot/image/upload', methods=['POST'])
def flow_shot_image_upload(flow_id):
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    try:
        shot_index = int(request.form.get('shot_index', ''))
    except ValueError:
        return jsonify({'success': False, 'error': '缺少 shot_index'}), 400
    if 'file' not in request.files or not request.files['file'].filename:
        return jsonify({'success': False, 'error': '未上传文件'}), 400
    base = ensure_drama_dirs(flow['drama_id'])
    file = request.files['file']
    ext = os.path.splitext(file.filename)[1].lower() or '.png'
    filename = f'shot_{shot_index}_ref_{uuid.uuid4().hex[:6]}{ext}'
    file.save(os.path.join(base, 'images', filename))
    image_url = f'/dramas/{flow["drama_id"]}/images/{filename}'
    with flow_lock:
        ov = flow.setdefault('shot_overrides', {}).setdefault(str(shot_index), {})
        ov['custom_images'] = (ov.get('custom_images') or []) + [{'image_url': image_url, 'local_file': filename}]
    _persist(flow_id)
    return jsonify({'success': True, 'image_url': image_url, 'filename': filename})


@flow_bp.route('/api/drama/flow/<flow_id>/shot/image/delete', methods=['POST'])
def flow_shot_image_delete(flow_id):
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    data = request.get_json(silent=True) or {}
    try:
        shot_index = int(data.get('shot_index'))
        image_index = int(data.get('image_index'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': '缺少参数'}), 400
    with flow_lock:
        ov = (flow.get('shot_overrides') or {}).get(str(shot_index)) or {}
        imgs = ov.get('custom_images') or []
        if 0 <= image_index < len(imgs):
            imgs.pop(image_index)
        remaining = len(imgs)
    _persist(flow_id)
    return jsonify({'success': True, 'remaining': remaining})


@flow_bp.route('/api/drama/flow/<flow_id>/shot/detail', methods=['GET'])
def flow_shot_detail(flow_id):
    """返回镜头的合成后详情（分镜定义 + 视频结果 + 覆盖的参考图）"""
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    try:
        shot_index = int(request.args.get('shot_index'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': '缺少 shot_index'}), 400
    sb_node = next((n for n in flow['nodes'].values() if n['type'] == 'storyboard' and n.get('output')), None)
    sh_node = next((n for n in flow['nodes'].values() if n['type'] == 'shots'), None)
    assets_node = next((n for n in flow['nodes'].values() if n['type'] == 'assets' and n.get('output')), None)
    shot = next((s for s in (sb_node['output']['shots'] if sb_node else [])
                 if s.get('shot_index') == shot_index), None)
    if not shot:
        return jsonify({'success': False, 'error': '镜头不存在'}), 404
    result = next((r for r in (sh_node['output'].get('results', []) if sh_node and sh_node.get('output') else [])
                   if r.get('shot_index') == shot_index), None)
    ov = (flow.get('shot_overrides') or {}).get(str(shot_index)) or {}
    auto_refs = []
    if assets_node:
        matched, primary = _match_assets(shot, assets_node['output']['assets'])
        auto_refs = [{'asset_name': a.get('name'), 'category': a.get('category'),
                      'image_url': a.get('image_url'), 'local_file': a.get('local_file')} for a in matched]
    return jsonify({'success': True, 'shot': shot, 'result': result,
                    'custom_images': ov.get('custom_images') or [], 'auto_refs': auto_refs,
                    'custom_prompt': ov.get('custom_prompt', '')})


# ---------- 合并 ----------

@flow_bp.route('/api/drama/flow/<flow_id>/merge', methods=['POST'])
def flow_merge(flow_id):
    """自定义顺序合并（无需 merge 节点存在，直接对 shots 结果操作）"""
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    data = request.get_json(silent=True) or {}
    shot_indices = data.get('shot_indices') or []
    merge_name = data.get('merge_name', 'custom')
    sh_node = next((n for n in flow['nodes'].values() if n['type'] == 'shots' and n.get('output')), None)
    if not sh_node:
        return jsonify({'success': False, 'error': '镜头视频未生成'}), 400
    results = sh_node['output']['results']
    completed = {r['shot_index'] for r in results if r.get('status') == 'completed' and r.get('local_file')}
    valid = [si for si in shot_indices if si in completed]
    if len(valid) < 2:
        return jsonify({'success': False, 'error': f'有效已完成镜头不足 2 个（{len(valid)}）'}), 400
    merged = merge_videos(flow['drama_id'], results, shot_order=valid,
                          output_prefix=f'merge_{merge_name}')
    if not merged:
        return jsonify({'success': False, 'error': '合并失败，请检查 ffmpeg 与日志'}), 500
    with flow_lock:
        flow.setdefault('custom_merges', []).append(
            {'name': merge_name, 'shot_indices': valid, 'merged_file': merged, 'at': time.time()})
    _persist(flow_id)
    return jsonify({'success': True, 'merged_file': merged, 'shot_indices': valid})


@flow_bp.route('/api/drama/flow/<flow_id>/reset', methods=['POST'])
def flow_reset(flow_id):
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    with flow_lock:
        for n in flow['nodes'].values():
            n.update({'status': 'pending', 'output': None, 'error': ''})
    _persist(flow_id)
    return jsonify({'success': True})


@flow_bp.route('/api/drama/flow/<flow_id>', methods=['DELETE'])
def flow_delete(flow_id):
    with flow_lock:
        flows.pop(flow_id, None)
        flow_stop_events.pop(flow_id, None)
    path = os.path.join(_flows_dir(), f'{flow_id}.json')
    if os.path.exists(path):
        os.remove(path)
    return jsonify({'success': True})


# ---------- 模板（只存图结构与参数，不存数据） ----------

@flow_bp.route('/api/drama/flow/templates', methods=['GET'])
def flow_templates_list():
    items = []
    for fn in os.listdir(_templates_dir()):
        if fn.endswith('.json'):
            try:
                with open(os.path.join(_templates_dir(), fn), 'r', encoding='utf-8') as f:
                    t = json.load(f)
                items.append({'name': fn[:-5], 'nodes': len(t.get('nodes', {})),
                              'created_at': t.get('created_at', 0)})
            except Exception:
                pass
    return jsonify({'success': True, 'templates': items})


@flow_bp.route('/api/drama/flow/<flow_id>/template/save', methods=['POST'])
def flow_template_save(flow_id):
    flow = _load_flow(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': '流不存在'}), 404
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or flow.get('name') or '未命名模板').strip()
    safe = ''.join(c for c in name if c.isalnum() or c in '_-一-龥')[:40] or 'unnamed'
    tpl = {'nodes': flow['nodes'], 'edges': flow['edges'],
           'params': flow['params'], 'created_at': time.time()}
    with open(os.path.join(_templates_dir(), f'{safe}.json'), 'w', encoding='utf-8') as f:
        json.dump(tpl, f, ensure_ascii=False, indent=1)
    return jsonify({'success': True, 'name': safe})


@flow_bp.route('/api/drama/flow/templates/<name>', methods=['DELETE'])
def flow_template_delete(name):
    safe = ''.join(c for c in name if c.isalnum() or c in '_-一-龥')
    path = os.path.join(_templates_dir(), f'{safe}.json')
    if os.path.exists(path):
        os.remove(path)
    return jsonify({'success': True})


# ---------- 启动回收：重启前已在云端生成的镜头任务 ----------

RECOVER_MAX_POLLS = 120          # 10s × 120 = 20 分钟，与 run_video_job 轮询上限一致


def _recovered_result(entry, local_file='', video_url='', error=''):
    si = entry.get('shot_index')
    return {'shot_index': si, 'status': 'completed' if local_file else 'failed',
            'local_file': local_file or None, 'video_url': video_url, 'error': error,
            'prompt': entry.get('prompt', ''), 'prompt_cn': entry.get('prompt_cn', ''),
            'primary_image': entry.get('primary_image', ''), 'recovered': True}


def _recover_finish(flow_id, entry, result):
    """写回 shots 节点 output 并清理 inflight"""
    si = entry.get('shot_index')
    flow = _load_flow(flow_id)
    if not flow:
        return
    with flow_lock:
        (flow.get('inflight') or {}).pop(str(si), None)
        nid = next((i for i, n in flow['nodes'].items() if n['type'] == 'shots'), None)
        if nid:
            node = flow['nodes'][nid]
            if node.get('output') is None:
                node['output'] = {'results': []}
            results = node['output'].setdefault('results', [])
            results[:] = [r for r in results if r.get('shot_index') != si]
            results.append(result)
    _persist(flow_id)
    if result['status'] == 'completed' and result.get('local_file'):
        try:
            sb = next((n for n in flow['nodes'].values()
                       if n['type'] == 'storyboard' and n.get('output')), None)
            shot = next((s for s in ((sb or {}).get('output') or {}).get('shots', [])
                         if s.get('shot_index') == si), None)
            if shot and shot.get('dialogue'):
                burn_chinese_subtitle(os.path.join(get_app_dir(), entry['save_subdir'],
                                                   result['local_file']), shot['dialogue'])
        except Exception as e:
            print(f'[短剧流] 回收镜头{si} 字幕烧录异常: {e}')
    print(f'[短剧流 {flow_id}] 回收镜头 {si} -> {result["status"]}')


def _recover_shot_task(flow_id, key, entry):
    """轮询一个在途云端任务直至有结论（后台线程）"""
    model = entry.get('video_model') or DEFAULT_VIDEO_MODEL
    base_url = get_vendor_base_url(model)
    headers = {'Authorization': f"Bearer {get_vendor_api_key(model, fallback_key=get_api_key())}",
               'Content-Type': 'application/json'}
    for _ in range(RECOVER_MAX_POLLS):
        if shutdown_event.wait(timeout=10):
            return  # 服务再次关闭：inflight 留在磁盘，下次启动继续回收
        try:
            poll = query_video_task(model, base_url, headers,
                                    task_id=entry.get('task_id'), video_id=entry.get('video_id'))
        except Exception:
            continue
        if poll.status_code == 404:
            _recover_finish(flow_id, entry, _recovered_result(entry, error='云端任务不存在或已过期'))
            return
        if poll.status_code != 200:
            continue
        try:
            pr = poll.json()
        except Exception:
            continue
        st = pr.get('status', '')
        if st == 'completed':
            v_video_id = pr.get('video_id', '') or entry.get('video_id', '')
            v_url = extract_video_url(pr)
            local = download_generated_video(model, base_url, headers, entry.get('task_id'),
                                             v_video_id, v_url, entry.get('save_subdir', 'videos'),
                                             f"shot_{entry.get('shot_index')}")
            _recover_finish(flow_id, entry,
                            _recovered_result(entry, local_file=local or '', video_url=v_url,
                                              error='' if local else '回收下载失败'))
            return
        if st == 'failed':
            _recover_finish(flow_id, entry, _recovered_result(entry, error=pr.get('error', '云端任务失败')))
            return
    _recover_finish(flow_id, entry, _recovered_result(entry, error='回收轮询超时(20分钟)'))


def recover_inflight_shots():
    """create_app 启动钩子：扫描已落盘 flow 的 inflight，救回已付费的云端结果"""
    try:
        count = 0
        for fn in os.listdir(_flows_dir()):
            if not fn.endswith('.json'):
                continue
            fid = fn[:-5]
            flow = _load_flow(fid)
            if not flow:
                continue
            for key, entry in list((flow.get('inflight') or {}).items()):
                print(f'[短剧流 {fid}] 恢复在途镜头任务 shot={entry.get("shot_index")} '
                      f'task={entry.get("task_id") or entry.get("video_id")}')
                threading.Thread(target=_recover_shot_task, args=(fid, key, entry), daemon=True).start()
                count += 1
        if count:
            print(f'[短剧流] 已启动 {count} 个镜头任务回收线程')
    except Exception as e:
        print(f'[短剧流] 启动回收异常: {e}')

