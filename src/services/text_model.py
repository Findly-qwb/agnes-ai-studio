"""
文本模型调用与 Prompt 模板模块
包含：call_text_model、JSON 解析、剧本/分镜/素材提示词模板、视频 prompt 构建
"""

import json
import requests
from ..config import get_text_base_url, get_vendor_base_url
from ..models import DEFAULT_TEXT_MODEL


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

def script_system_prompt():
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


def storyboard_system_prompt(shot_duration):
    return f"""你是一位专业的分镜师。将短剧剧本改写为分镜脚本。
要求：
1. 每个分镜时长约 {shot_duration} 秒
2. 每个分镜需要详细描述画面内容
3. 包含镜头类型（特写/中景/远景/跟拍等）
4. 必须严格输出 JSON 格式
5. 英文 prompt 必须避免任何暴力、血腥、武器、色情、政治敏感等内容，确保符合AI视频生成平台的内容安全策略
6. 动作场景用温和的方式表达，例如用"追逐"代替"打斗"，用"对话"代替"争吵"
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


def assets_system_prompt():
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


def sanitize_video_prompt(prompt):
    """清洗视频 prompt，移除可能触发内容安全策略的关键词"""
    prompt_lower = prompt.lower()
    cleaned = prompt
    for word in _CONTENT_POLICY_WORDS:
        if word.lower() in prompt_lower:
            cleaned = cleaned.replace(word, '').replace(word.lower(), '').replace(word.title(), '')
    cleaned = ' '.join(cleaned.split())
    return cleaned


def build_video_prompt(shot, shot_assets):
    """根据分镜和参考素材构建视频生成 prompt（强调角色外观一致性）"""
    prompt = shot.get('prompt_en', '') or shot.get('scene_desc', '')
    
    # 添加中文对话要求
    dialogue = shot.get('dialogue', '')
    if dialogue:
        prompt = f"{prompt}. Dialogue in Chinese: \"{dialogue}\""
    
    if shot_assets:
        char_descs = []
        scene_descs = []
        prop_descs = []
        for a in shot_assets:
            desc = a.get('desc', '')
            if not desc:
                continue
            for term in ['three views', 'three-view', 'character design sheet', 'design board',
                         'front view', 'side view', 'back view', 'orthographic', 'design sheet',
                         'multiple views', 'close-up detail', 'detail showcase']:
                desc = desc.replace(term, '').replace(term.title(), '')
            desc = ' '.join(desc.split())
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
    
    prompt = f"{prompt}. Natural cinematic scene only, no design sheet, no character layout, no three-view."
    prompt = sanitize_video_prompt(prompt)
    return prompt
