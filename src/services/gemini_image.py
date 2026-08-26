"""
Gemini 原生图片生成服务
通过 google-genai SDK 调用 gemini-* 图像模型，返回图片字节并保存到本地。

用法：generate_gemini_image(prompt, model, subdir='pictures', prefix='gemini')
返回 (relative_url, local_filename)，relative_url 形如 /pictures/xxx.png。

注意：该模型走 Google 原生 generateContent API（response_modalities=['image']），
与 OpenAI 兼容的 /images/generations 协议不同，无法经 get_vendor_base_url 复用。
"""

import os
import uuid
import json
from datetime import datetime
from ..config import get_app_dir, get_config_path

# Gemini 图像模型默认值
DEFAULT_GEMINI_IMAGE_MODEL = 'models/gemini-3.1-flash-lite-image'


def get_gemini_api_key():
    """从 config.json 读取 gemini_api_key"""
    config_file = get_config_path()
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            try:
                return json.load(f).get('gemini_api_key', '') or ''
            except json.JSONDecodeError:
                return ''
    return ''


def is_gemini_image(model):
    """判断模型是否为 Gemini 图像模型"""
    return bool(model) and ('gemini' in model.lower() or model.startswith('models/'))


def _image_part_from_url(image_url, types):
    """将参考图转成 Gemini Part（支持 data URL / 远程 URL / 本地 /pictures/ 路径）"""
    import base64
    import mimetypes

    image_bytes = None
    mime_type = None

    if isinstance(image_url, str) and image_url.startswith('data:'):
        header, _, b64 = image_url.partition(',')
        mime_type = header[5:header.find(';')]
        image_bytes = base64.b64decode(b64)
    elif isinstance(image_url, str) and image_url.startswith('/pictures/'):
        filepath = os.path.join(get_app_dir(), image_url.lstrip('/'))
        with open(filepath, 'rb') as f:
            image_bytes = f.read()
        mime_type = mimetypes.guess_type(filepath)[0] or 'image/png'
    else:
        import requests
        resp = requests.get(image_url, timeout=60)
        resp.raise_for_status()
        image_bytes = resp.content
        mime_type = resp.headers.get('Content-Type', 'image/png')

    return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)


def _save_images(resp, subdir, prefix):
    """从 Gemini 响应提取图片字节并保存到本地

    Returns:
        (relative_url, local_filename)；无图片数据则抛出异常
    """
    image_data = None
    for candidate in (resp.candidates or []):
        for part in (candidate.content.parts if candidate.content else []):
            if getattr(part, 'inline_data', None) and part.inline_data.data:
                image_data = part.inline_data.data
                break
        if image_data:
            break

    if not image_data:
        raise RuntimeError('Gemini 响应中未包含图片数据')

    target_dir = os.path.join(get_app_dir(), subdir)
    os.makedirs(target_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'{prefix}_{timestamp}_{uuid.uuid4().hex[:8]}.png'
    filepath = os.path.join(target_dir, filename)
    with open(filepath, 'wb') as f:
        f.write(image_data)

    print(f"[Gemini图片] 保存成功 {subdir}/{filename} ({len(image_data) // 1024}KB)")
    return f'/{subdir}/{filename}', filename


def generate_gemini_image(prompt, model=DEFAULT_GEMINI_IMAGE_MODEL, subdir='pictures', prefix='gemini'):
    """调用 Gemini 图像模型文生图并保存到本地

    Args:
        prompt: 图片描述
        model: Gemini 图像模型名（如 models/gemini-3.1-flash-lite-image）
        subdir: 保存子目录（如 pictures 或 dramas/xxx/images）
        prefix: 文件名前缀

    Returns:
        (relative_url, local_filename)；失败抛异常
    """
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError('未配置 Gemini API Key（config.json 的 gemini_api_key）')

    try:
        from google import genai
    except ImportError:
        raise RuntimeError('缺少 google-genai 依赖，请运行: pip install google-genai')

    client = genai.Client(api_key=api_key)
    config = {
        'response_modalities': ['image'],
        'temperature': 1,
        'max_output_tokens': 65536,
    }

    try:
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
    except Exception as e:
        raise RuntimeError(f'Gemini 图片生成失败: {e}')

    return _save_images(resp, subdir, prefix)


def generate_gemini_image_with_reference(prompt, image_url, model=DEFAULT_GEMINI_IMAGE_MODEL,
                                         subdir='pictures', prefix='gemini_edit'):
    """调用 Gemini 图像模型图生图并保存到本地（参考图 + 编辑指令）

    Args:
        prompt: 编辑指令
        image_url: 参考图（data URL、远程 URL 或本地 /pictures/ 路径）
        model: Gemini 图像模型名
        subdir: 保存子目录
        prefix: 文件名前缀

    Returns:
        (relative_url, local_filename)；失败抛异常
    """
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError('未配置 Gemini API Key（config.json 的 gemini_api_key）')

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError('缺少 google-genai 依赖，请运行: pip install google-genai')

    client = genai.Client(api_key=api_key)
    config = {
        'response_modalities': ['image'],
        'temperature': 1,
        'max_output_tokens': 65536,
    }

    try:
        resp = client.models.generate_content(
            model=model,
            contents=[prompt, _image_part_from_url(image_url, types)],
            config=config,
        )
    except Exception as e:
        raise RuntimeError(f'Gemini 图生图失败: {e}')

    return _save_images(resp, subdir, prefix)


if __name__ == '__main__':
    assert is_gemini_image('models/gemini-3.1-flash-lite-image')
    assert is_gemini_image('gemini-flash-latest')
    assert not is_gemini_image('agnes-image-2.1-flash')
    assert not is_gemini_image('')
    print('gemini_image 自检通过')