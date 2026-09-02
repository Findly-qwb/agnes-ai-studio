"""
素材参考图生成 —— 旧一键短剧（routes/drama.py）与节点流（routes/drama_flow.py）共用的唯一实现。

覆盖：角色风格模板、单素材 prompt 构建、生图 API 提交（限流退避 + Gemini 原生分支）、
镜头→素材匹配。两条链路以前各自抄了一份，节点流版本的措辞与修复更新；
统一到这里后，改一处两边同时生效。
"""

import json
import time

from ..config import get_custom_model_config, get_vendor_api_key, get_vendor_base_url
from .gemini_image import is_gemini_image, generate_gemini_image
from .text_model import sanitize_image_prompt
from .video_gen import download_and_save_file

# ==================== 角色风格样式映射 ====================
CHARACTER_STYLES = {
    'anime': {
        'name': '动漫卡通',
        'character': (
            "high quality anime character design sheet, detailed illustration, "
            "vibrant colors, clean lineart, soft shading, professional concept art. "
            "soft natural studio lighting, warm color temperature. "
            "9:16 vertical composition, pure white minimalist background, premium character design board layout. "
        ),
        'scene': (
            "high quality anime scene design, detailed illustration, vibrant colors, "
            "soft shading, professional concept art, warm color temperature. "
            "soft natural studio lighting. "
        ),
        'prop': (
            "high quality anime prop design sheet, detailed illustration, vibrant colors, "
            "soft shading, professional concept art, warm color temperature. "
            "soft natural studio lighting. "
        ),
    },
    'realistic': {
        'name': '写实真人',
        'character': (
            "photorealistic character design sheet, hyper-detailed real human reference, "
            "professional photography style, natural skin texture, realistic lighting. "
            "studio lighting setup, 8K ultra HD quality. "
            "9:16 vertical composition, pure white minimalist background, premium character design board layout. "
        ),
        'scene': (
            "photorealistic scene design, hyper-detailed environment, "
            "professional photography style, natural lighting, 8K ultra HD quality. "
            "realistic textures and materials. "
        ),
        'prop': (
            "photorealistic prop design sheet, hyper-detailed object reference, "
            "professional product photography style, studio lighting, 8K ultra HD quality. "
            "realistic textures and materials. "
        ),
    },
    'pixar3d': {
        'name': '皮克斯3D',
        'character': (
            "Pixar 3D style character design sheet, cute cartoon character, "
            "smooth 3D rendering, soft global illumination, vibrant saturated colors. "
            "Disney animation style, rounded shapes, big expressive eyes. "
            "9:16 vertical composition, pure white minimalist background, premium character design board layout. "
        ),
        'scene': (
            "Pixar 3D style scene design, cute cartoon environment, "
            "smooth 3D rendering, soft global illumination, vibrant saturated colors. "
            "Disney animation style. "
        ),
        'prop': (
            "Pixar 3D style prop design sheet, cute cartoon object, "
            "smooth 3D rendering, soft global illumination, vibrant saturated colors. "
            "Disney animation style. "
        ),
    },
    'watercolor': {
        'name': '水彩手绘',
        'character': (
            "beautiful watercolor painting character design sheet, soft brush strokes, "
            "delicate color bleeding effects, hand-painted illustration style. "
            "artistic watercolor textures, warm pastel tones. "
            "9:16 vertical composition, pure white minimalist background, premium character design board layout. "
        ),
        'scene': (
            "beautiful watercolor painting scene design, soft brush strokes, "
            "delicate color bleeding effects, hand-painted illustration style. "
            "artistic watercolor textures, warm pastel tones. "
        ),
        'prop': (
            "beautiful watercolor painting prop design sheet, soft brush strokes, "
            "delicate color bleeding effects, hand-painted illustration style. "
            "artistic watercolor textures, warm pastel tones. "
        ),
    },
    'ink': {
        'name': '中国水墨',
        'character': (
            "Chinese ink painting style character design sheet, traditional sumi-e brush strokes, "
            "elegant black ink on rice paper, minimalist composition, zen aesthetics. "
            "subtle color accents, artistic calligraphy elements. "
            "9:16 vertical composition, pure white minimalist background, premium character design board layout. "
        ),
        'scene': (
            "Chinese ink painting style scene design, traditional sumi-e brush strokes, "
            "elegant black ink on rice paper, minimalist composition, zen aesthetics. "
            "subtle color accents. "
        ),
        'prop': (
            "Chinese ink painting style prop design sheet, traditional sumi-e brush strokes, "
            "elegant black ink on rice paper, minimalist composition, zen aesthetics. "
            "subtle color accents. "
        ),
    },
    'semi_realistic': {
        'name': '半写实插画',
        'character': (
            "semi-realistic digital painting character design sheet, detailed illustration, "
            "realistic proportions with stylized features, smooth rendering. "
            "professional concept art, balanced between realism and stylization. "
            "9:16 vertical composition, pure white minimalist background, premium character design board layout. "
        ),
        'scene': (
            "semi-realistic digital painting scene design, detailed illustration, "
            "realistic proportions with stylized features, smooth rendering. "
            "professional concept art, balanced between realism and stylization. "
        ),
        'prop': (
            "semi-realistic digital painting prop design sheet, detailed illustration, "
            "realistic proportions with stylized features, smooth rendering. "
            "professional concept art, balanced between realism and stylization. "
        ),
    },
}

DEFAULT_CHARACTER_STYLE = 'anime'


def get_style_base(category, character_style=None):
    """根据分类和风格获取基础样式提示词"""
    style = CHARACTER_STYLES.get(character_style, CHARACTER_STYLES['anime'])
    return style.get(category, style['character'])


def build_character_image_prompt(desc, character_style=None):
    """根据角色描述自动识别角色类型（植物/动物/人类），生成对应的图 prompt，返回 (prompt, size)"""
    desc_lower = desc.lower()

    # 检测角色类型
    # 植物关键词
    plant_keywords = ['flower', 'rose', 'tree', 'plant', 'leaf', 'seed', 'root', 'stem', 'branch',
                      'grass', 'vine', 'bush', 'shrub', 'bloom', 'petal', 'bud', 'blossom',
                      '花', '玫瑰', '树', '植物', '叶', '种子', '根', '茎', '枝', '草', '藤',
                      '灌木', '花苞', '花瓣', '花蕾', '开花', '发芽', '竹', '松', '柳', '桃',
                      '菊', '兰', '莲', '荷', '牡丹', '向日葵', '百合', '郁金香']
    # 动物关键词
    animal_keywords = ['cat', 'dog', 'bird', 'fish', 'rabbit', 'horse', 'deer', 'bear', 'lion',
                       'tiger', 'wolf', 'fox', 'mouse', 'rat', 'snake', 'frog', 'turtle', 'whale',
                       'dolphin', 'eagle', 'hawk', 'owl', 'butterfly', 'bee', 'ant', 'spider',
                       '猫', '狗', '鸟', '鱼', '兔', '马', '鹿', '熊', '狮', '虎', '狼', '狐',
                       '鼠', '蛇', '蛙', '龟', '鲸', '海豚', '鹰', '猫头鹰', '蝴蝶', '蜂', '蚁',
                       '蜘蛛', '鸡', '鸭', '鹅', '猪', '牛', '羊', '猴', '象', '企鹅', '鹦鹉']

    is_plant = any(kw in desc_lower for kw in plant_keywords)
    is_animal = any(kw in desc_lower for kw in animal_keywords)

    base_style = get_style_base('character', character_style)

    if is_plant and not is_animal:
        # 植物角色
        return (
            f"{base_style}"
            f"Plant character design: show the plant in its natural form at various growth stages. "
            f"Left side: large-scale full-body illustration of the plant in its prime state. "
            f"Right top: front/side/back views showing the plant from different angles. "
            f"Right middle: close-up of the most distinctive feature (flower bud, leaf pattern, seed texture). "
            f"Left bottom: root system or base detail showcase. "
            f"Right bottom: texture details of petals, leaves, bark, or surface features. "
            f"Plant description: {desc}. "
            f"Same plant throughout, shape color and features fully consistent, no deformation. "
            f"Natural growth pose, rigorous botanical accuracy."
        ), '768x1344'
    elif is_animal and not is_plant:
        # 动物角色
        return (
            f"{base_style}"
            f"Animal character design: show the animal character with expressive features. "
            f"Left side: large-scale full-body illustration in standing or natural pose. "
            f"Right top: front/side/back three-view orthographic. "
            f"Right middle: face close-up with expressive eyes, below it detail shots of ears, paws, tail. "
            f"Left bottom: paw or claw detail showcase. "
            f"Right bottom: fur/feather/scale texture, markings and color pattern details. "
            f"Animal description: {desc}. "
            f"Same animal throughout, fur color markings and features fully consistent, no deformation. "
            f"Natural pose, rigorous anatomical structure."
        ), '768x1344'
    else:
        # 人类角色（默认）
        return (
            f"{base_style}"
            f"natural warm skin tone with healthy complexion, soft skin texture, "
            f"lifelike appearance, natural facial features. "
            f"Left side: large-scale front full-body illustration. "
            f"Right top: front/side/back three-view orthographic. "
            f"Right middle: one front face close-up, below it 5 small expression close-ups including 1 side face. "
            f"Left bottom: hand detail showcase (clear fingers, no extra or missing fingers). "
            f"Right bottom: clothing, accessories, hair detail close-ups. "
            f"Character description: {desc}. "
            f"Same character throughout, facial features hairstyle and clothing fully consistent, no deformation, no distortion. "
            f"Standard standing pose, rigorous structure."
        ), '768x1344'


def build_asset_image_prompt(asset, character_style=None):
    """单个素材 asset → (img_prompt, img_size)。措辞取节点流版本（更严格：无人的场景/道具约束更强）。
    prompt_en 同样拼风格前缀，否则 character_style 对 prompt_en 素材被静默忽略（节点流已修的 bug）"""
    category = asset.get('category', 'characters')
    desc = asset.get('desc', '')
    prompt_en = asset.get('prompt_en', '')
    style = character_style or DEFAULT_CHARACTER_STYLE
    if prompt_en:
        img_prompt = f"{get_style_base(category[:-1], style)}{prompt_en}"
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
    return sanitize_image_prompt(img_prompt), img_size


def request_asset_image(image_model, img_prompt, img_size, api_key, save_subdir, safe_name, abort_check=None):
    """调用生图 API，最多 3 次尝试（429/503/433 限流阶梯退避），返回 (image_url, local_file)。
    彻底失败抛 RuntimeError（含最后一次错误）；abort_check 返回 True 时抛「已中止」"""
    def aborted():
        return bool(abort_check and abort_check())

    base_url = get_vendor_base_url(image_model)
    key = get_vendor_api_key(image_model, fallback_key=api_key)
    import requests
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    last_err = '未知错误'
    for attempt in range(3):
        try:
            # Gemini 原生图像模型直接本地生成保存，不走 /images/generations；
            # 自定义模型即使名称含 gemini 也不走此路径
            if is_gemini_image(image_model) and not get_custom_model_config(image_model):
                return generate_gemini_image(img_prompt, image_model, save_subdir, safe_name)
            resp = requests.post(f'{base_url}/images/generations', headers=headers,
                                 json={'model': image_model, 'prompt': img_prompt, 'size': img_size},
                                 timeout=180)
            if resp.status_code == 200:
                result = resp.json()
                data = result.get('data') or []
                if data and data[0].get('url'):
                    image_url = data[0]['url']
                    local = download_and_save_file(image_url, save_subdir, safe_name, 'png')
                    return image_url, local
                last_err = f'响应无 url: {json.dumps(result, ensure_ascii=False)[:200]}'
            elif resp.status_code in (429, 503, 433):
                last_err = f'限流 {resp.status_code}'
                for _ in range(15 * (attempt + 1)):
                    if aborted():
                        raise RuntimeError('已中止')
                    time.sleep(1)
                continue
            else:
                last_err = f'API {resp.status_code}: {resp.text[:200]}'
        except RuntimeError:
            raise
        except Exception as e:
            last_err = f'{type(e).__name__}: {e}'
        if aborted():
            raise RuntimeError('已中止')
        time.sleep(3)
    raise RuntimeError(f'素材 [{safe_name}] 生图失败: {last_err}')


def match_shot_assets(shot, assets):
    """按角色/场景/道具名匹配镜头素材，返回 (matched_assets, primary_image)。primary 缺失时回退第一个角色参考"""
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
