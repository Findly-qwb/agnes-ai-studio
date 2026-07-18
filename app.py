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
import subprocess
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

@app.route('/dramas/<path:filename>')
def serve_drama_file(filename):
    """服务短剧输出文件（图片/视频）"""
    app_dir = get_app_dir()
    dramas_dir = os.path.join(app_dir, 'dramas')
    os.makedirs(dramas_dir, exist_ok=True)
    return send_from_directory(dramas_dir, filename)

# ==================== 配置 ====================
BASE_URL = "https://apihub.agnes-ai.com/v1"

# 存储视频任务状态 (内存存储，重启后丢失)
video_tasks = {}
task_lock = threading.Lock()

# 全局关闭事件：用于通知所有后台线程退出
shutdown_event = threading.Event()

# ==================== 短剧生成 ====================
drama_tasks = {}
drama_lock = threading.Lock()
# ---------- 厂商 Base URL 映射（通用，文本/图片/视频共用）----------
VENDOR_BASE_URLS = {
    'agnes': 'https://apihub.agnes-ai.com/v1',
    'deepseek': 'https://api.deepseek.com/v1',
    'gpt': 'https://api.openai.com/v1',
    'qwen': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    'doubao': 'https://ark.cn-beijing.volces.com/api/v3',
    'minimax': 'https://api.minimaxi.chat/v1',
}

# 兼容旧名称
TEXT_MODEL_BASE_URLS = VENDOR_BASE_URLS

def get_vendor_from_model(model):
    """从模型名称推断厂商标识"""
    if not model:
        return 'agnes'
    model_lower = model.lower()
    for prefix in VENDOR_BASE_URLS:
        if prefix == 'agnes':
            continue
        if model_lower.startswith(prefix):
            return prefix
    return 'agnes'

def get_vendor_base_url(model):
    """根据模型名称获取厂商 Base URL（优先使用自定义配置）"""
    config_file = get_config_path()
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 检查是否有该厂商的自定义 Base URL
        vendor = get_vendor_from_model(model)
        custom_key = f'{vendor}_base_url'
        custom_url = data.get(custom_key, '').strip()
        if custom_url:
            return custom_url
        # 兼容旧的 text_base_url 配置
        if vendor in ('deepseek', 'gpt', 'qwen', 'doubao'):
            text_url = data.get('text_base_url', '').strip()
            if text_url:
                return text_url
    return VENDOR_BASE_URLS.get(get_vendor_from_model(model), BASE_URL)

def get_vendor_api_key(model, fallback_key=None):
    """根据模型名称获取厂商 API Key（优先使用厂商专用 Key，回退到全局 Key）"""
    vendor = get_vendor_from_model(model)
    config_file = get_config_path()
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 优先使用厂商专用 Key
        vendor_key = data.get(f'{vendor}_api_key', '').strip()
        if vendor_key:
            return vendor_key
        # 兼容旧的 text_api_key
        if vendor in ('deepseek', 'gpt', 'qwen', 'doubao'):
            text_key = data.get('text_api_key', '').strip()
            if text_key:
                return text_key
    # 回退到传入的 fallback 或全局 Key
    if fallback_key:
        return fallback_key
    return get_api_key()

# 兼容旧函数名
def get_text_base_url(model=None):
    return get_vendor_base_url(model)

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

def ensure_drama_dirs(drama_id):
    """确保短剧输出目录存在"""
    app_dir = get_app_dir()
    base = os.path.join(app_dir, 'dramas', drama_id)
    for sub in ('images', 'videos'):
        os.makedirs(os.path.join(base, sub), exist_ok=True)
    return base

def call_text_model(system_prompt, user_prompt, api_key, model=None, max_tokens=4096):
    """调用文本模型 (OpenAI chat completions 兼容接口)
    
    Args:
        model: 模型名称，默认使用 DEFAULT_TEXT_MODEL
        api_key: 对应厂商的 API Key
    """
    if model is None:
        model = DEFAULT_TEXT_MODEL
    base_url = get_text_base_url(model)
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        'max_tokens': max_tokens,
        'temperature': 0.7
    }
    print(f"[文本模型] model={model}, base_url={base_url}")
    resp = requests.post(
        f'{base_url}/chat/completions',
        headers=headers,
        json=payload,
        timeout=120
    )
    if resp.status_code == 200:
        result = resp.json()
        content = result['choices'][0]['message']['content']
        return content
    else:
        raise Exception(f"文本模型 API 错误 ({resp.status_code}): {resp.text}")

def parse_json_from_text(text):
    """从文本模型响应中解析 JSON（兼容 markdown 代码块包裹）"""
    text = text.strip()
    if text.startswith('```'):
        lines = text.split('\n')
        start = 1
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip().startswith('```'):
                end = i
                break
        text = '\n'.join(lines[start:end]).strip()
    return json.loads(text)

# ---------- 短剧 Prompt 模板 ----------

def _script_system_prompt():
    return """你是一位专业的短剧编剧。根据用户描述生成简短的短剧剧本。
要求：
1. 剧本要简短，2-3个场景，每个场景1-3个角色动作/对话
2. 角色数量控制在1-3个
3. 场景描述要具体、视觉化
4. 必须严格输出 JSON 格式，不要包含其他文字

输出 JSON 格式：
{
  "title": "短剧标题",
  "characters": [{"name": "角色名", "description": "外貌特征描述"}],
  "scenes": [{"description": "场景环境描述"}],
  "props": [{"name": "道具名", "description": "道具描述"}],
  "story": "简短的故事梗概，2-3句话"
}"""

def _storyboard_system_prompt(shot_duration):
    return f"""你是一位专业的分镜师。将短剧剧本改写为分镜脚本。
要求：
1. 每个分镜时长约 {shot_duration} 秒
2. 每个分镜需要详细描述画面内容
3. 包含镜头类型（特写/中景/远景/跟拍等）
4. 必须严格输出 JSON 格式
5. 英文 prompt 必须避免任何暴力、血腥、武器、色情、政治敏感等内容，确保符合AI视频生成平台的内容安全策略
6. 动作场景用温和的方式表达，例如用“追逐”代替“打斗”，用“对话”代替“争吵”
7. 【重要】每个分镜的 prompt_en 中必须包含该镜头中所有角色的完整外观描述（发型、发色、服装、肤色等），确保不同分镜中同一角色的外观保持一致
8. 角色外观描述要具体、固定，例如："a young woman with long black hair, wearing a white dress, light skin" 而不是 "a woman"
9. 【重要】如果分镜中有对话或文字内容（如字幕、标牌、屏幕文字等），必须使用中文
10. 【重要】画面描述应该是自然场景，不要出现角色设定图、三视图、设计板等元素

输出 JSON 格式：
{{
  "shots": [
    {{
      "shot_index": 1,
      "scene_desc": "画面描述",
      "characters": ["角色名"],
      "action": "动作描述",
      "camera": "镜头类型",
      "dialogue": "中文对话内容（如有）",
      "prompt_en": "Detailed English prompt for AI video generation, MUST include full character appearance details (hair style, hair color, clothing, skin color etc.) for every character in this shot. If there is dialogue or text, specify it must be in Chinese. Natural scene only, NO design sheet or three-view layout."
    }}
  ]
}}"""

def _assets_system_prompt():
    return """请严格按照以下要求执行：

1. 首先仔细通读并深度理解输入的全部文本内容；

2. 从文本中精准提取角色、场景、道具三类画面提示词，全程固定纯白色纯色背景，不添加任何背景元素；

3. 【角色提取强制要求】需完整拆解并提取每一位角色的全套细节，包含：
- 年龄特征（精准标注年龄段/具体年龄、气质年龄感）
- 外貌特征（五官细节、脸型、肤色、神态、身材体态、面部细节、妆容细节等）
- 发型细节（发型款式、发色、发长、发饰样式、发饰位置、发丝质感、编发/盘发细节等）
- 服饰全套细节（服饰形制、款式、颜色、面料材质、纹样图案、配色渐变、配饰、鞋履、穿搭层次、服饰版型细节等）

4. 【场景提取要求】仅提取文本中明确提及的场景核心元素，场景描述词；

5. 【道具提取要求】精准提取文本中出现的所有手持/摆放/随身道具，包含道具样式、材质、颜色、细节特征；

6. 输出格式清晰分类：分「角色画面提示词」「场景画面提示词」「道具画面提示词」三大板块，角色需按单人逐条拆分，细节完整不遗漏、不篡改、不脑补文本外信息，语言为精准画面描述词，适配AIGC生成逻辑。

必须严格输出 JSON 格式：
{  "characters": [{"name": "角色名", "desc": "详细的英文视觉特征描述，包含年龄、外貌、发型、服饰等全部细节，white background"}],
  "scenes": [{"name": "场景名", "desc": "详细的英文场景视觉描述，white background"}],
  "props": [{"name": "道具名", "desc": "详细的英文道具视觉描述，包含样式、材质、颜色、细节特征，white background"}]
}

注意：
- 每个角色必须单独拆分，不要合并
- 描述必须用英文，适合AI图像生成
- 每个描述末尾加上 "white background, character design sheet, three views"
- 不要遗漏任何角色、场景或道具"""

# 视频模型内容安全敏感词列表（用于 prompt 清洗）
_CONTENT_POLICY_WORDS = [
    'violence', 'violent', 'bloody', 'blood', 'gore', 'murder', 'kill', 'killing',
    'weapon', 'gun', 'knife', 'sword', 'bomb', 'explosion', 'shoot', 'shooting',
    'nude', 'naked', 'sexual', 'porn', 'erotic', 'drug', 'alcohol abuse',
    'torture', 'suicide', 'self-harm', 'racist', 'discrimination',
    '暴力', '血腥', '杀戮', '武器', '枪支', '色情', '毒品',
]

def _sanitize_video_prompt(prompt):
    """清洗视频 prompt，移除可能触发内容安全策略的关键词"""
    prompt_lower = prompt.lower()
    cleaned = prompt
    for word in _CONTENT_POLICY_WORDS:
        if word.lower() in prompt_lower:
            cleaned = cleaned.replace(word, '').replace(word.lower(), '').replace(word.title(), '')
    # 清理多余空格
    cleaned = ' '.join(cleaned.split())
    return cleaned

def _build_video_prompt(shot, shot_assets):
    """根据分镜和参考素材构建视频生成 prompt（强调角色外观一致性）"""
    prompt = shot.get('prompt_en', '') or shot.get('scene_desc', '')
    
    # 添加中文对话要求
    dialogue = shot.get('dialogue', '')
    if dialogue:
        prompt = f"{prompt}. Dialogue in Chinese: \"{dialogue}\""
    
    if shot_assets:
        # 按类别分组构建详细描述（排除设计图/三视图相关术语）
        char_descs = []
        scene_descs = []
        prop_descs = []
        for a in shot_assets:
            desc = a.get('desc', '')
            if not desc:
                continue
            # 清除描述中可能包含的三视图/设定板相关词汇
            for term in ['three views', 'three-view', 'character design sheet', 'design board',
                         'front view', 'side view', 'back view', 'orthographic', 'design sheet',
                         'multiple views', 'close-up detail', 'detail showcase']:
                desc = desc.replace(term, '').replace(term.title(), '')
            desc = ' '.join(desc.split())  # 清理多余空格
            if not desc:
                continue
            cat = a.get('category', '')
            name = a.get('name', '')
            if cat == 'characters':
                char_descs.append(f"{name}: {desc}")
            elif cat == 'scenes':
                scene_descs.append(desc)
            elif cat == 'props':
                prop_descs.append(desc)
        
        consistency_parts = []
        if char_descs:
            consistency_parts.append("Character appearance (MUST match exactly): " + "; ".join(char_descs))
        if prop_descs:
            consistency_parts.append("Props: " + "; ".join(prop_descs))
        if scene_descs:
            consistency_parts.append("Scene: " + "; ".join(scene_descs))
        
        if consistency_parts:
            prompt = f"{prompt}. {' | '.join(consistency_parts)}. Maintain visual consistency with reference images."
    
    # 强调自然场景，不要设计图
    prompt = f"{prompt}. Natural cinematic scene only, no design sheet, no character layout, no three-view."
    
    # 清洗敏感内容
    prompt = _sanitize_video_prompt(prompt)
    return prompt

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
    """获取/保存 API Key 配置（支持各厂商独立 Key）"""
    config_file = get_config_path()
    
    def _mask_key(key):
        if not key:
            return ''
        return key[:8] + '****' + key[-4:] if len(key) > 12 else '****'
    
    if request.method == 'GET':
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 返回时隐藏所有 key
            result = {}
            for k, v in data.items():
                if k.endswith('_api_key') or k == 'api_key':
                    result[k] = ''
                    result[f'{k}_masked'] = _mask_key(v) if v else ''
                elif k.endswith('_base_url'):
                    result[k] = v
                else:
                    result[k] = v
            return jsonify(result)
        return jsonify({'api_key': '', 'api_key_masked': ''})

    elif request.method == 'POST':
        data = request.get_json()
        # 读取现有配置
        config = {}
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        
        # 保存全局 Key
        api_key = data.get('api_key', '').strip()
        if api_key:
            config['api_key'] = api_key
        
        # 保存各厂商 Key 和 Base URL
        vendor_keys = ['text_api_key', 'deepseek_api_key', 'doubao_api_key', 'minimax_api_key', 'qwen_api_key']
        vendor_urls = ['text_base_url', 'deepseek_base_url', 'doubao_base_url', 'minimax_base_url', 'qwen_base_url']
        
        for key_field in vendor_keys:
            val = data.get(key_field, '').strip()
            if val:
                config[key_field] = val
            elif key_field in data:
                config.pop(key_field, None)
        
        for url_field in vendor_urls:
            val = data.get(url_field, '').strip()
            if val:
                config[url_field] = val
            elif url_field in data:
                config.pop(url_field, None)
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        return jsonify({'success': True, 'message': '配置已保存'})


def get_api_key():
    """读取保存的 API Key"""
    config_file = get_config_path()
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('api_key', '')
    return ''

def get_text_api_key():
    """读取文本模型专用 API Key，未设置则回退到全局 Key"""
    config_file = get_config_path()
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        text_key = data.get('text_api_key', '').strip()
        if text_key:
            return text_key
    return get_api_key()


# ==================== 图片生成 ====================

@app.route('/api/image/generate', methods=['POST'])
def generate_image():
    """文生图"""
    data = request.get_json()
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'success': False, 'error': '请输入图片描述'}), 400

    size = data.get('size', '1024x1024')
    model = data.get('model', 'agnes-image-2.1-flash')
    save_local = data.get('save_local', True)
    
    # 根据模型获取厂商 API Key 和 Base URL
    api_key = get_vendor_api_key(model)
    if not api_key:
        return jsonify({'success': False, 'error': '请先配置 API Key'}), 401
    base_url = get_vendor_base_url(model)

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
            f'{base_url}/images/generations',
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
    prompt = data.get('prompt', '').strip()
    image_url = data.get('image_url', '').strip()
    if not prompt or not image_url:
        return jsonify({'success': False, 'error': '请输入描述和图片URL'}), 400

    # 将本地图片路径转为 base64
    image_url = resolve_image_url(image_url)

    size = data.get('size', '1024x768')
    save_local = data.get('save_local', True)
    model = data.get('model', 'agnes-image-2.0-flash')
    
    # 根据模型获取厂商 API Key 和 Base URL
    api_key = get_vendor_api_key(model)
    if not api_key:
        return jsonify({'success': False, 'error': '请先配置 API Key'}), 401
    base_url = get_vendor_base_url(model)

    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': model,
            'prompt': prompt,
            'size': size,
            'extra_body': {
                'tags': ['img2img'],
                'image': [image_url],
                'response_format': 'url'
            }
        }

        resp = requests.post(
            f'{base_url}/images/generations',
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
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'success': False, 'error': '请输入视频描述'}), 400

    width = data.get('width', 1152)
    height = data.get('height', 768)
    num_frames = data.get('num_frames', 121)
    frame_rate = data.get('frame_rate', 24)
    image_url = data.get('image_url', '')  # 可选：图生视频
    model = data.get('model', 'agnes-video-v2.0')
    # 将本地图片路径转为 base64
    if image_url:
        image_url = resolve_image_url(image_url)
    negative_prompt = data.get('negative_prompt', '')
    seed = data.get('seed')
    
    # 根据模型获取厂商 API Key 和 Base URL
    api_key = get_vendor_api_key(model)
    if not api_key:
        return jsonify({'success': False, 'error': '请先配置 API Key'}), 401
    base_url = get_vendor_base_url(model)

    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': model,
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
            f'{base_url}/videos',
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
                args=(task_id, api_key, model),
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


def _download_and_save_file(url, subdir, prefix, ext, max_retries=3):
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

    # 生成唯一文件名：前缀_时间戳_UUID.扩展名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    short_uuid = uuid.uuid4().hex[:8]
    filename = f"{prefix}_{timestamp}_{short_uuid}.{ext}"
    filepath = os.path.join(target_dir, filename)

    for attempt in range(max_retries):
        try:
            print(f"[下载] {subdir}/{filename} (尝试 {attempt+1}/{max_retries}) url={url[:100]}...")
            resp = requests.get(url, timeout=180, stream=True)
            resp.raise_for_status()

            # 检查 Content-Type 是否是视频/图片（防止下载到错误页面）
            content_type = resp.headers.get('Content-Type', '')
            if ext == 'mp4' and 'video' not in content_type and 'octet-stream' not in content_type and 'mp4' not in content_type:
                print(f"[下载警告] Content-Type 不是视频: {content_type}")

            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            # 检查文件大小
            file_size = os.path.getsize(filepath)
            if file_size < 1000:  # 小于 1KB 可能是错误响应
                print(f"[下载警告] 文件太小 ({file_size} bytes)，可能是错误响应")
                if attempt < max_retries - 1:
                    os.remove(filepath)
                    import time
                    time.sleep(2)
                    continue
                else:
                    os.remove(filepath)
                    return None

            print(f"[保存成功] {subdir}/{filename} ({file_size // 1024}KB)")
            return filename
        except Exception as e:
            print(f"[下载失败] {subdir}/{filename} 尝试{attempt+1}: {e}")
            # 清理失败的文件
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except:
                    pass
            if attempt < max_retries - 1:
                import time
                time.sleep(3)
    return None


def poll_video_status(task_id, api_key, model=None):
    """后台轮询视频生成状态"""
    headers = {'Authorization': f'Bearer {api_key}'}
    base_url = get_vendor_base_url(model) if model else BASE_URL
    max_polls = 120  # 最多轮询 120 次
    poll_interval = 10  # 每 10 秒轮询一次

    for i in range(max_polls):
        # 使用 Event.wait 代替 time.sleep，可被 shutdown_event 中断
        if shutdown_event.wait(timeout=poll_interval):
            print(f"[轮询] 收到关闭信号，退出轮询 task_id={task_id}")
            return
        try:
            # 方式1：标准 OpenAI 兼容接口
            resp = requests.get(
                f'{base_url}/videos/{task_id}',
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
                                result.get('video_url')
                                or result.get('url')
                                or result.get('output_url')
                                or result.get('video')
                                or result.get('remixed_from_video_id')
                                or ''
                            )
                            # 尝试从 data 字段获取 (兼容 dict 和 list 两种格式)
                            if not video_url and isinstance(result.get('data'), dict):
                                video_url = result['data'].get('url', '') or result['data'].get('video_url', '') or result['data'].get('video', '')
                            # 如果 result.data 是列表形式
                            if not video_url and isinstance(result.get('data'), list) and len(result['data']) > 0:
                                video_url = result['data'][0].get('url', '') or result['data'][0].get('video_url', '')
                            # 尝试从 metadata 中提取
                            if not video_url and isinstance(result.get('metadata'), dict):
                                meta = result['metadata']
                                video_url = meta.get('video_url', '') or meta.get('url', '') or meta.get('output_url', '')
                            # 尝试通过 content 端点获取
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
            # 如果程序正在关闭，直接退出
            if shutdown_event.is_set():
                return
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


# ==================== 视频拼接 (ffmpeg) ====================

def get_ffmpeg_path():
    """获取 ffmpeg 可执行文件路径（优先系统 PATH，其次 imageio-ffmpeg 内置）"""
    # 检查系统 PATH
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return 'ffmpeg'
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # 使用 imageio-ffmpeg 内置的二进制文件
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        if ffmpeg_exe and os.path.exists(ffmpeg_exe):
            return ffmpeg_exe
    except ImportError:
        pass
    return None

def merge_videos(drama_id, video_results):
    """使用 ffmpeg 将多个分镜视频拼接为一个完整视频
    
    Args:
        drama_id: 短剧 ID
        video_results: 视频结果列表（包含 local_file 字段）
    
    Returns:
        合并后的文件名，失败返回 None
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        print(f"[短剧 {drama_id}] 警告: 未找到 ffmpeg，跳过视频拼接")
        return None
    
    # 收集成功的视频文件（按镜头顺序）
    success_videos = []
    for v in sorted(video_results, key=lambda x: x.get('shot_index', 0)):
        if v.get('status') == 'completed' and v.get('local_file'):
            app_dir = get_app_dir()
            full_path = os.path.join(app_dir, 'dramas', drama_id, 'videos', v['local_file'])
            if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                success_videos.append(full_path)
    
    if len(success_videos) < 2:
        print(f"[短剧 {drama_id}] 成功视频少于 2 个，跳过拼接")
        return None
    
    print(f"[短剧 {drama_id}] 开始拼接 {len(success_videos)} 个视频...")
    
    # 创建 concat 文件列表
    app_dir = get_app_dir()
    videos_dir = os.path.join(app_dir, 'dramas', drama_id, 'videos')
    list_file = os.path.join(videos_dir, 'concat_list.txt')
    
    try:
        with open(list_file, 'w', encoding='utf-8') as f:
            for video_path in success_videos:
                # ffmpeg concat 需要正斜杠或转义
                safe_path = video_path.replace('\\', '/')
                f.write(f"file '{safe_path}'\n")
        
        # 输出文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'merged_{timestamp}.mp4'
        output_path = os.path.join(videos_dir, output_file)
        
        # 执行 ffmpeg 拼接
        cmd = [
            ffmpeg,
            '-f', 'concat',
            '-safe', '0',
            '-i', list_file,
            '-c', 'copy',  # 直接复制流，不重新编码（速度快）
            '-y',  # 覆盖输出文件
            output_path
        ]
        
        print(f"[短剧 {drama_id}] 执行: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            file_size = os.path.getsize(output_path) // 1024
            print(f"[短剧 {drama_id}] 拼接成功: {output_file} ({file_size}KB)")
            return output_file
        else:
            print(f"[短剧 {drama_id}] 拼接失败: {result.stderr[:500]}")
            # 如果 copy 模式失败，尝试重新编码模式
            print(f"[短剧 {drama_id}] 尝试重新编码模式...")
            cmd_reencode = [
                ffmpeg,
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-y',
                output_path
            ]
            result2 = subprocess.run(cmd_reencode, capture_output=True, text=True, timeout=600)
            if result2.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size = os.path.getsize(output_path) // 1024
                print(f"[短剧 {drama_id}] 重新编码拼接成功: {output_file} ({file_size}KB)")
                return output_file
            else:
                print(f"[短剧 {drama_id}] 重新编码也失败: {result2.stderr[:500]}")
                return None
    except subprocess.TimeoutExpired:
        print(f"[短剧 {drama_id}] 拼接超时")
        return None
    except Exception as e:
        print(f"[短剧 {drama_id}] 拼接异常: {e}")
        return None
    finally:
        # 清理临时列表文件
        if os.path.exists(list_file):
            try:
                os.remove(list_file)
            except:
                pass

# ==================== 短剧生成 - 流水线 ====================

def drama_pipeline(drama_id, api_key, text_api_key=None):
    """短剧生成 4 步流水线（后台线程执行）
    
    Args:
        api_key: 全局 API Key（用于图片/视频模型）
        text_api_key: 文本模型专用 API Key（未设置则回退到全局 Key）
    """
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
                _script_system_prompt(),
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
                _storyboard_system_prompt(shot_duration),
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

        # ---- Step 3: 提取素材 + 生成三视图 ----
        if _is_shutdown(): return
        print(f"[短剧 {drama_id}] Step 3: 提取素材并生成三视图...")
        _update(status='step3', step='step3', message='正在提取角色/场景/道具特征...')

        try:
            assets_text = call_text_model(
                _assets_system_prompt(),
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
            _update(assets=all_assets, message=f'提取到 {len(all_assets)} 个素材，正在生成三视图...')
        except Exception as e:
            _update(status='failed', message=f'素材提取失败: {e}')
            return

        # 生成素材参考图（角色设定图/场景图/道具图）
        drama_base = ensure_drama_dirs(drama_id)
        for idx, asset in enumerate(all_assets):
            if _is_shutdown(): return
            category = asset.get('category', 'characters')
            cat_label = {'characters': '角色', 'scenes': '场景', 'props': '道具'}.get(category, '素材')
            _update(message=f'生成{cat_label}图 ({idx+1}/{len(all_assets)}): {asset["name"]}...')
            try:
                desc = asset.get('desc', '')
                # 根据素材类别使用不同的提示词模板
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
                    img_size = '768x1344'  # 9:16 竖版
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
                    img_size = '1344x768'  # 16:9 横版
                else:  # props
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
                    img_size = '768x1344'  # 9:16 竖版
                
                headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
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
                            local = _download_and_save_file(image_url, f'dramas/{drama_id}/images', f'asset_{idx}', 'png')
                            asset['local_file'] = local
                print(f"[短剧 {drama_id}] 素材 {idx+1} [{asset['name']}]: {'OK' if asset['image_url'] else 'FAIL'}")
            except Exception as e:
                print(f"[短剧 {drama_id}] 素材图片生成失败: {e}")
            with drama_lock:
                drama_tasks[drama_id]['assets'] = list(all_assets)

        _update(message=f'三视图生成完成，{sum(1 for a in all_assets if a["image_url"])}/{len(all_assets)} 成功')

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

            # 匹配本镜头需要的参考素材图片（收集所有相关素材）
            shot_chars = [c.lower().strip() for c in shot.get('characters', [])]
            shot_asset_list = []
            primary_image = None  # 主要参考图（传给视频 API 的单张图）
            
            # 匹配角色素材
            for asset in all_assets:
                if not asset.get('image_url'):
                    continue
                asset_name = asset.get('name', '').lower().strip()
                # 精确匹配或包含匹配
                if any(asset_name in c or c in asset_name for c in shot_chars):
                    shot_asset_list.append(asset)
                    if not primary_image:
                        primary_image = asset['image_url']
            
            # 匹配场景素材
            for asset in all_assets:
                if not asset.get('image_url') or asset.get('category') != 'scenes':
                    continue
                asset_name = asset.get('name', '').lower().strip()
                scene_desc = shot.get('scene_desc', '').lower()
                if asset_name and asset_name in scene_desc:
                    shot_asset_list.append(asset)
                    if not primary_image:
                        primary_image = asset['image_url']
            
            # 匹配道具素材
            for asset in all_assets:
                if not asset.get('image_url') or asset.get('category') != 'props':
                    continue
                asset_name = asset.get('name', '').lower().strip()
                action_desc = shot.get('action', '').lower()
                if asset_name and asset_name in action_desc:
                    shot_asset_list.append(asset)
            
            # 如果还没有参考图，使用第一个有图片的角色素材
            if not primary_image:
                for asset in all_assets:
                    if asset.get('image_url') and asset.get('category') == 'characters':
                        primary_image = asset['image_url']
                        shot_asset_list.append(asset)
                        break

            video_prompt = _build_video_prompt(shot, shot_asset_list)

            # 提交视频任务
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

                # 轮询本镜头视频
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
                                # 打印完整响应以便调试
                                full_resp = json.dumps(pr_data, ensure_ascii=False)
                                print(f"[短剧 {drama_id}] 镜头 {shot_idx+1} 完成，完整响应: {full_resp}")
                                
                                # 尝试从多种可能的字段提取视频 URL
                                v_url = (pr_data.get('video_url') or pr_data.get('url')
                                    or pr_data.get('output_url') or pr_data.get('video') or '')
                                # 尝试从 data 字段提取
                                if not v_url and isinstance(pr_data.get('data'), dict):
                                    v_url = pr_data['data'].get('url', '') or pr_data['data'].get('video_url', '') or pr_data['data'].get('video', '')
                                if not v_url and isinstance(pr_data.get('data'), list) and len(pr_data['data']) > 0:
                                    v_url = pr_data['data'][0].get('url', '') or pr_data['data'][0].get('video_url', '')
                                # 尝试从 result 字段提取
                                if not v_url and isinstance(pr_data.get('result'), dict):
                                    v_url = pr_data['result'].get('url', '') or pr_data['result'].get('video_url', '')
                                # 尝试从 metadata 中提取
                                if not v_url and isinstance(pr_data.get('metadata'), dict):
                                    meta = pr_data['metadata']
                                    v_url = meta.get('video_url', '') or meta.get('url', '') or meta.get('output_url', '')
                                    if not v_url and isinstance(meta.get('size_mapping'), dict):
                                        v_url = meta['size_mapping'].get('video_url', '') or meta['size_mapping'].get('url', '')
                                # 如果还是没有 URL，尝试通过 content 端点获取
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
                                    local_fn = _download_and_save_file(v_url, f'dramas/{drama_id}/videos', f'shot_{shot_idx}', 'mp4')
                                else:
                                    print(f"[短剧 {drama_id}] 镜头 {shot_idx+1} 警告: 未提取到视频URL")
                                # 只有本地文件保存成功才算完成
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


# ==================== 短剧生成 - API ====================

@app.route('/api/drama/start', methods=['POST'])
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

    # 根据文本模型获取对应厂商的 API Key
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


@app.route('/api/drama/models', methods=['GET'])
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


@app.route('/api/drama/status/<drama_id>', methods=['GET'])
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


@app.route('/api/drama/list', methods=['GET'])
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


# ==================== 关闭服务 ====================

@app.route('/api/shutdown', methods=['POST'])
def api_shutdown():
    """关闭服务：通知所有后台线程退出，然后停止 Flask"""
    print("[关闭] 收到关闭请求，正在停止服务...")
    shutdown_event.set()
    # 延迟 0.5 秒让响应先返回给浏览器
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

    print("  提示: 按 Ctrl+C 可停止服务")
    print("=" * 60)

    try:
        # 生产模式运行（不开启 debug，避免 reloader 冲突）
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n[关闭] 收到 Ctrl+C，正在停止服务...")
        shutdown_event.set()
        print("[关闭] 服务已停止")


if __name__ == '__main__':
    main()
