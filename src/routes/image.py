"""
图片生成 + 上传路由
"""

import os
import uuid
import json
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify

from ..config import get_vendor_api_key, get_vendor_base_url, get_custom_model_config, resolve_image_url, ensure_output_dirs, get_config_path
from ..services.gemini_image import is_gemini_image, generate_gemini_image
from ..services.text_model import translate_cn_to_en, is_mostly_chinese
from ..models import DEFAULT_TEXT_MODEL


# 中文→英文不是直译：原描述常自相矛盾（"照片风格"+"拟人化Q版角色"），
# 直译会把矛盾原样带过去，模型按写实先验执行就出真动物照片。这里做意图改写。
_IMAGE_REWRITE_SYSTEM = (
    "You are an expert AI image prompt engineer. Convert the user's Chinese description into ONE English prompt "
    "ready for a text-to-image model. Rules: "
    "1) Preserve every intent and detail of the original. "
    "2) Detect the IMPLIED style and state it explicitly: anthropomorphic/cartoon/Q-version characters mean stylized "
    "rendering (e.g. '3D render, Pixar style, plush fur texture, anthropomorphic character'), NOT a real photo; "
    "only keep photorealism when the subject is genuinely real. "
    "3) Resolve contradictions in favor of the subject's nature (an anthropomorphic grumpy bunny is a character, "
    "even if the text says 'photo'); rewrite misleading words like 照片/photorealistic accordingly (e.g. 'cinematic shot of the character'). "
    "4) Structure: [subject + appearance] + [expression/action/position] + [scene] + [style] + [lighting] + [composition] + [quality words]. "
    "Output ONLY the prompt itself, no explanation or quotes."
)


def _maybe_translate(prompt, data):
    """中文提示词自动改写为英文图像提示词，translate_prompt=false 可关；失败回退原文"""
    if data.get('translate_prompt', True) and is_mostly_chinese(prompt):
        return translate_cn_to_en(prompt, get_vendor_api_key(DEFAULT_TEXT_MODEL), DEFAULT_TEXT_MODEL,
                                  system=_IMAGE_REWRITE_SYSTEM)
    return prompt
from ..services.video_gen import download_and_save_file
from ..services.text_model import call_text_model
from ..models import DEFAULT_TEXT_MODEL

image_bp = Blueprint('image', __name__)


@image_bp.route('/api/prompt/enhance', methods=['POST'])
def enhance_prompt():
    """提示词优化：用文本模型把短描述扩写成高质量提示词"""
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    mode = data.get('mode', 'image')
    if not prompt:
        return jsonify({'success': False, 'error': '请输入提示词'}), 400

    # 从配置读取提示词优化模型，默认文本模型
    enhance_model = DEFAULT_TEXT_MODEL
    try:
        with open(get_config_path(), 'r', encoding='utf-8') as f:
            enhance_model = json.load(f).get('prompt_enhance_model') or DEFAULT_TEXT_MODEL
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    api_key = get_vendor_api_key(enhance_model)
    if not api_key:
        return jsonify({'success': False, 'error': '请先配置 API Key'}), 401

    system_prompts = {
        'image': '你是一位专业的 AI 图像提示词优化师。请将用户输入的简短描述扩写为一段高质量、结构化的英文提示词，结构为：[主体] + [场景/背景] + [风格] + [光照] + [构图] + [画质要求]。只输出扩写后的提示词本身，不要任何解释、引号或前缀。',
        'img2img': '你是一位专业的 AI 图像编辑提示词优化师。用户提供参考图并描述想要做的修改，请将输入扩写为高质量、结构化的英文编辑提示词，按照以下结构组织：[需要改变的要求] + [新的风格/场景] + [需要添加或移除的元素] + [需要保留的元素]（主体、构图、人物表情/姿态等）。只输出编辑提示词本身，不要任何解释、引号或前缀。',
        'video': 'You are an expert AI video prompt optimizer. Expand the user\'s brief description into a detailed, cinematic English video prompt covering: subject, setting, camera movement, lighting, mood, and quality. Output only the optimized prompt itself, with no explanations, quotes, or prefixes.',
        'story': '你是资深短剧策划。请把用户的一句话点子扩写为一段具体、有画面感的中文短剧描述：包含主要角色及其目标、核心冲突与转折、场景与时代氛围、整体视觉风格。保持用户原意，不要发明与点子无关的设定。只输出描述本身，不要任何解释、标题或引号。',
    }

    try:
        enhanced = call_text_model(system_prompts.get(mode, system_prompts['image']), prompt, api_key, model=enhance_model, max_tokens=1024)
        return jsonify({'success': True, 'enhanced': enhanced, 'model': enhance_model})
    except Exception as e:
        return jsonify({'success': False, 'error': f'优化失败: {e}'}), 500


@image_bp.route('/api/image/generate', methods=['POST'])
def generate_image():
    """文生图"""
    data = request.get_json()
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'success': False, 'error': '请输入图片描述'}), 400

    size = data.get('size', '1024x1024')
    ratio = data.get('ratio')
    model = data.get('model', 'agnes-image-2.5-flash')
    save_local = data.get('save_local', True)

    try:
        # Gemini 原生图像模型：走 Google generateContent，不依赖厂商/全局 key 路由
        # 自定义模型即使名称含 gemini 也不走此路径，沿用自定义 base_url/key
        if is_gemini_image(model) and not get_custom_model_config(model):
            relative_url, local_filename = generate_gemini_image(prompt, model)
            return jsonify({
                'success': True,
                'image_url': relative_url,
                'local_file': local_filename,
                'raw_response': {'note': 'gemini-image', 'model': model}
            })

        api_key = get_vendor_api_key(model)
        if not api_key:
            return jsonify({'success': False, 'error': '请先配置 API Key'}), 401
        prompt = _maybe_translate(prompt, data)
        base_url = get_vendor_base_url(model)

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': model,
            'prompt': prompt,
            'size': size
        }
        if ratio:
            payload['ratio'] = ratio

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

            local_filename = None
            if save_local and image_url:
                local_filename = download_and_save_file(
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


@image_bp.route('/api/image/img2img', methods=['POST'])
def img2img():
    """图生图 / 图片编辑"""
    data = request.get_json()
    prompt = data.get('prompt', '').strip()
    image_url = data.get('image_url', '').strip()
    if not prompt or not image_url:
        return jsonify({'success': False, 'error': '请输入描述和图片URL'}), 400

    image_url = resolve_image_url(image_url)

    size = data.get('size', '1024x768')
    ratio = data.get('ratio')
    save_local = data.get('save_local', True)
    model = data.get('model', 'agnes-image-2.5-flash')

    try:
        # Gemini 原生图像模型：图生图通过多模态 contents 传入
        # 自定义模型即使名称含 gemini 也不走此路径，沿用自定义 base_url/key
        if is_gemini_image(model) and not get_custom_model_config(model):
            from ..services.gemini_image import generate_gemini_image_with_reference
            relative_url, local_filename = generate_gemini_image_with_reference(prompt, image_url, model)
            return jsonify({
                'success': True,
                'image_url': relative_url,
                'local_file': local_filename,
                'raw_response': {'note': 'gemini-image-edit', 'model': model}
            })

        prompt = _maybe_translate(prompt, data)

        api_key = get_vendor_api_key(model)
        if not api_key:
            return jsonify({'success': False, 'error': '请先配置 API Key'}), 401
        base_url = get_vendor_base_url(model)

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': model,
            'prompt': prompt,
            'size': size,
            'extra_body': {
                'image': [image_url],
                'response_format': 'url'
            }
        }
        if ratio:
            payload['ratio'] = ratio

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

            local_filename = None
            if save_local and image_url_out:
                local_filename = download_and_save_file(
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


@image_bp.route('/api/upload/image', methods=['POST'])
def upload_image():
    """上传本地图片，返回可访问的 URL"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '未找到上传文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '文件名为空'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    allowed_exts = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
    if ext not in allowed_exts:
        return jsonify({'success': False, 'error': f'不支持的图片格式: {ext}'}), 400

    _, pictures_dir = ensure_output_dirs()
    unique_name = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
    save_path = os.path.join(pictures_dir, unique_name)
    file.save(save_path)

    return jsonify({
        'success': True,
        'filename': unique_name,
        'url': f'/pictures/{unique_name}'
    })
