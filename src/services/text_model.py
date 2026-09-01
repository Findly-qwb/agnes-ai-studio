"""
文本模型调用与 Prompt 模板模块
包含：call_text_model、JSON 解析、剧本/分镜/素材提示词模板、视频 prompt 构建
"""

import json
import time
import requests
from ..config import get_text_base_url, get_vendor_base_url
from ..models import DEFAULT_TEXT_MODEL


def call_text_model(system_prompt, user_prompt, api_key, model=None, max_tokens=4096, temperature=0.7, abort_check=None):
    """调用文本模型 (OpenAI chat completions 兼容接口)
    
    Args:
        model: 模型名称，默认使用 DEFAULT_TEXT_MODEL
        api_key: 对应厂商的 API Key（Ollama 不需要）
        temperature: 创作类 0.7，结构化输出（分镜）建议 0.4
        abort_check: 可选回调，返回 True 时在重试等待/请求间隙中止（抛「已中止」）
    """
    if model is None:
        model = DEFAULT_TEXT_MODEL
    base_url = get_text_base_url(model)
    
    # Ollama 不需要 API Key，使用哑认证
    from ..config import get_vendor_from_model
    is_ollama = get_vendor_from_model(model) == 'ollama'
    
    headers = {
        'Content-Type': 'application/json'
    }
    if not is_ollama:
        headers['Authorization'] = f'Bearer {api_key}'
    
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        'max_tokens': max_tokens,
        'temperature': temperature
    }
    # Ollama 本地模型使用更长的超时时间（本地推理较慢）
    req_timeout = 600 if is_ollama else 300
    print(f"[文本模型] model={model}, base_url={base_url}{' (Ollama本地)' if is_ollama else ''}")

    def _check_abort():
        if abort_check and abort_check():
            raise RuntimeError('已中止')

    def _sleep_with_abort(seconds):
        for _ in range(int(seconds)):
            _check_abort()
            time.sleep(1)

    max_retries = 3
    for attempt in range(max_retries + 1):
        _check_abort()
        try:
            resp = requests.post(
                f'{base_url}/chat/completions',
                headers=headers,
                json=payload,
                timeout=req_timeout
            )
            if resp.status_code == 200:
                result = resp.json()
                content = result['choices'][0]['message']['content']
                return content
            elif resp.status_code in (429, 502, 503, 504, 433) and 'model_not_found' not in resp.text and attempt < max_retries:
                # TPM 限额通常在下一个分钟窗口恢复，优先使用服务端的等待建议。
                # model_not_found 是永久错误，重试无意义，直接快速失败
                retry_after = resp.headers.get('Retry-After')
                wait_sec = int(retry_after) if retry_after and retry_after.isdigit() else (60 if resp.status_code == 429 else 10 * (attempt + 1))
                print(f"[文本模型] 请求受限或网关错误 {resp.status_code}，{wait_sec}秒后重试 ({attempt+1}/{max_retries})...")
                _sleep_with_abort(wait_sec)
                continue
            else:
                raise Exception(f"文本模型 API 错误 ({resp.status_code}): {resp.text[:500]}")
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                wait_sec = 10 * (attempt + 1)
                print(f"[文本模型] 请求超时，{wait_sec}秒后重试 ({attempt+1}/{max_retries})...")
                _sleep_with_abort(wait_sec)
                continue
            raise Exception("文本模型 API 请求超时（已重试3次）")
        except requests.exceptions.ConnectionError as conn_err:
            if attempt < max_retries:
                wait_sec = 10 * (attempt + 1)
                print(f"[文本模型] 连接错误，{wait_sec}秒后重试 ({attempt+1}/{max_retries})...")
                _sleep_with_abort(wait_sec)
                continue
            raise Exception(f"文本模型 API 连接失败: {conn_err}")


def parse_json_from_text(text):
    """从文本模型响应中解析 JSON（兼容 markdown 代码块包裹，支持截断修复）"""
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
    # 第一次尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 第二次尝试：修复截断的 JSON（未闭合的字符串和括号）
    repaired = _repair_truncated_json(text)
    if repaired is not None:
        return repaired
    raise ValueError(f"JSON 解析失败，响应长度 {len(text)} 字符，前 200 字符: {text[:200]}")


def _repair_truncated_json(text):
    """尝试修复被截断的 JSON（模型输出被 max_tokens 截断时）"""
    # 策略：逐字符解析，跟踪括号栈，在截断处尝试闭合
    stack = []  # 存储未闭合的括号: '{' 或 '['
    in_string = False
    escape_next = False
    last_complete_pos = -1  # 最后一个完整值的位置
    i = 0
    
    while i < len(text):
        ch = text[i]
        
        if escape_next:
            escape_next = False
            i += 1
            continue
            
        if ch == '\\' and in_string:
            escape_next = True
            i += 1
            continue
            
        if ch == '"':
            in_string = not in_string
            if not in_string:
                # 字符串结束，检查是否是一个完整值
                # 向后看，跳过空白后应该是 , } ] 之一
                j = i + 1
                while j < len(text) and text[j] in ' \t\n\r':
                    j += 1
                if j < len(text) and text[j] in ',}]':
                    last_complete_pos = j
            i += 1
            continue
            
        if in_string:
            i += 1
            continue
            
        # 不在字符串内
        if ch in '{[':
            stack.append(ch)
            i += 1
            continue
        elif ch in '}]':
            if stack:
                stack.pop()
            i += 1
            continue
        elif ch == ',':
            # 逗号分隔符，前一个值完成
            last_complete_pos = i
            i += 1
            continue
        else:
            i += 1
            continue
    
    # 辅助函数：根据未闭合的括号栈生成闭合字符串（逆序闭合）
    def _closing_for_stack(stk):
        return ''.join('}' if c == '{' else ']' for c in reversed(stk))
    
    # 辅助函数：重新计算给定文本的未闭合括号栈
    def _unclosed_stack(txt):
        stk = []
        in_s = False
        es = False
        for c in txt:
            if es:
                es = False
                continue
            if c == '\\' and in_s:
                es = True
                continue
            if c == '"':
                in_s = not in_s
                continue
            if not in_s:
                if c in '{[':
                    stk.append(c)
                elif c in '}]':
                    if stk:
                        stk.pop()
        return stk
    
    # 到达末尾，JSON 被截断
    # 尝试从最后完成的位置截断并闭合
    if last_complete_pos > 0:
        candidate = text[:last_complete_pos + 1]
        # 确保末尾是 } ] 或 , 之一
        while candidate and candidate[-1] in ' \t\n\r':
            candidate = candidate[:-1]
        if candidate and candidate[-1] == ',':
            candidate = candidate[:-1]
        # 用栈计算未闭合的括号，逆序闭合
        stk = _unclosed_stack(candidate)
        candidate += _closing_for_stack(stk)
        try:
            result = json.loads(candidate)
            print(f"[JSON修复] 截断的 JSON 已自动修复（保留到位置 {last_complete_pos}）")
            return result
        except json.JSONDecodeError:
            pass
    
    # 如果上面的方法失败，尝试更激进的方法：直接在末尾闭合
    candidate = text
    if in_string:
        # 如果文本以未转义的反斜杠结尾（escape_next=True），
        # 直接加 " 会被 \ 转义成 \"，字符串无法闭合
        # 需要先加一个 \ 来转义前一个 \，再加 " 闭合字符串
        if escape_next:
            candidate += '\\'
        candidate += '"'
    # 用栈计算未闭合的括号，逆序闭合
    stk = _unclosed_stack(candidate)
    candidate += _closing_for_stack(stk)
    try:
        result = json.loads(candidate)
        print(f"[JSON修复] 截断的 JSON 已激进修复")
        return result
    except json.JSONDecodeError:
        pass
    
    return None


# ---------- 短剧 Prompt 模板 ----------

def story_system_prompt():
    return """你是一位才华横溢的短剧作家，擅长将简单的描述转化为引人入胜的故事。
根据用户提供的描述，创作一个 300～500 字的故事梗概。

要求：
1. 字数严格控制在 300～500 字之间
2. 故事要有完整的起承转合，情节紧凑、节奏明快
3. 主角可以是人、动物、植物、非生物或任何虚构实体，请准确理解用户描述的主体，赋予其鲜明的个性和情感
4. 场景描写要具有画面感，便于后续转化为分镜
5. 包含核心冲突和高潮，结尾有余韵或反转
6. 直接输出故事正文，不要标题、不要任何额外说明文字

【视频生成纪律】这个故事最终要用 AI 视频模型拍出来，模型的短板非常具体：
7. 主角不超过 3 个，故事发生的场景不超过 4 个——每多一个角色、一个场景，画面一致性和生成成本翻倍
8. 冲突必须「可拍摄」：用看得见的动作和反应表达（拦路、抢回、僵住、转身跑开、愣在原地），禁止用内心独白、读信、看屏幕这类无法外化的活动推进剧情
9. 情绪必须外化：不写「他很伤心」，写「他蹲在屋檐下，雨水顺着下巴一滴一滴落」——给后续分镜一个能直接画的画面"""


def script_system_prompt():
    return """你是一位专业的短剧编剧，擅长将故事改编为拍摄剧本。
请将下面提供的故事内容，1:1 精准还原为专业短剧剧本。

【重要：角色类型识别】
- 故事中的主角/角色可能是人、动物、植物、非生物（如石头、水滴、星星）或任何虚构实体
- 你必须准确理解每个角色的本质类型，不要将所有角色默认为人类
- 对于非人类角色，要保留其原始特征（如材质、形态、颜色、大小），不要强行赋予人类外观
- 非人类角色的「台词」和「情感」通过拟人化方式呈现，但外观描述必须符合其本质

【格式规范】
1. 每场戏以编号开头，格式：「编号 日/夜、内/外、场景名」
   - 日/夜：标明白天或夜晚
   - 内/外：标明室内或室外
2. 紧接列出该场出场角色，格式：「角色：角色A、角色B…」
   - 人类角色可标注年龄，如「小明（25岁）」
   - 非人类角色标注其本质类型和关键特征，如「小树苗（嫩绿色，约30厘米高）」、「老石头（灰色，表面粗糙）」
3. 画面描述用「▲」符号开头，描述要尽可能详细、具有画面感
4. 特写镜头必须在画面描述中明确标注，如：「▲面部特写：…」或「▲（特写）…」
5. 角色旁白/内心独白用「角色名vo：…」格式
6. 角色对话用「角色名（情绪/动作）：台词内容」格式
7. 有 vo 的台词，必须搭配相应的画面描述
8. 需要额外搭配画面时，用「搭配画面：…」补充说明
9. 字幕用「【出字幕：内容】」格式
10. 每个角色在首次出场时要详细描述其外观特征：
    - 人类角色：发型、服饰、肤色、体态等
    - 动物角色：物种、毛色、体型、特殊标记等
    - 植物角色：种类、颜色、大小、形态、生长状态等
    - 非生物角色：材质、颜色、形状、大小、表面质感等

【内容要求】
- 故事中的每个情节、每句台词都要还原，不遗漏、不删减
- 画面描述要详细，让导演和摄影师能直接据此拍摄
- 情绪、动作、镜头运动都要写清楚
- 直接输出剧本文本，不要包含任何额外说明或解释

【视频生成纪律】这个剧本会被逐场拆成 3~18 秒的 AI 生成视频：
- 每个「▲画面描述」= 一个可拍摄的单镜头：一个主体、一个动作。不写「A 拿起 B 递给 C」这类精确连续物理交互（AI 视频模型必崩），拆成两拍：「▲A 拾起 B，特写」→「▲A 将 B 递向 C，中景」
- 台词 vo 尽量少用：视频模型不会对口型，关键信息优先用画面承载，vo 只在无法避免时使用，且每次不超过两句
- 情绪外化：不写「她意识到真相」，写「▲她猛地抬头，手里的杯子歪了，水洒在桌面上」
- 每个场景首次出现时，用一句话固定它的光照氛围（如「深夜，月光从破窗斜切进来，冷蓝灰色调」），后续同场景沿用同一句"""


def storyboard_system_prompt(shot_duration):
    return f"""你是一位专业的分镜师。将短剧剧本改写为分镜脚本。

【基本规则】
1. 每个分镜时长约 {shot_duration} 秒
2. 每个分镜需要详细描述画面内容
3. 必须严格输出 JSON 格式
4. 英文 prompt 必须避免任何暴力、血腥、武器、色情、政治敏感等内容，确保符合AI视频生成平台的内容安全策略；动作场景用温和的方式表达，例如用"追逐"代替"打斗"
5. 【重要】每个分镜的 prompt_en 中必须包含该镜头中所有角色的完整外观描述，确保不同分镜中同一角色的外观保持一致。角色外观描述要具体、固定，按角色类型写：
   - 人类：发型、发色、服装、肤色等，如 "a young woman with long black hair, wearing a white dress"
   - 动物：物种、毛色、体型等，如 "a small orange cat with white paws"
   - 植物/非生物：种类、材质、颜色、形态等，如 "a smooth grey stone with a round shape"
6. 【重要】分镜中的对话、字幕等内容用中文；画面描述是自然场景，不要出现设定图、三视图、设计板等元素；prompt_en 中如有对话或字幕，必须写明 "Chinese subtitle" 或 "speak in Chinese"
7. 【景别与运镜】camera 字段用固定词表（中文）：大远景/全景/中景/近景/特写/大特写，可加运镜：固定、推、拉、摇、跟拍、手持。
   对应的英文短语（extreme wide shot / wide shot / medium shot / medium close-up / close-up / extreme close-up；static shot / push in / pull out / pan / tracking shot / handheld）必须原样出现在该分镜的 prompt_en 里——景别和运镜写进提示词，不要赌模型自己选
8. 【位置状态连续性】action 必须写明每个画内角色的位置和姿态（如"已坐在船舱内"、"站在桥头"、"正抬脚上船"）。
   相邻分镜的人物位置必须是连续剧情状态：上一镜上了船，下一镜不得又出现在岸上——视频模型只按字面画，位置状态不写清就会"上了船的人被画回岸上"
9. 【台词预算】单个分镜的 dialogue 中文长度不得超过 {int(shot_duration * 4.5)} 字（约 {shot_duration} 秒口播量），超出的台词必须拆成多个连续分镜
10. 【入画大资产】船、马车、宅门、招牌等"会被镜头拍到的大型资产"若出现在画面，scene_desc 必须写明它的完整外观（材质、颜色、新旧程度）——不写清，每一镜都会发明一个全新的道具

【视频模型能力边界】——最重要，直接决定成片会不会崩：
A. 只写「常见动作」：转身、走动、奔跑、抬头、低头、蹲下、推门、拥抱、愣住、颤抖、趴下、凝视——模型见过千万次的动作。
   禁止「精确物理交互」：拿起特定的物品、递东西给别人、系扣子、打开锁、抓住某人的手腕、用手指着某样东西——这些在生成的视频里必然崩坏。
   ✗ "父亲把信放在桌上，米奥跳起来用爪子按住信角"（三个精确交互，必崩）
   ✓ 拆成两镜：「桌上放着一封信，米奥趴在信旁，特写：它眯起眼睛」→「米奥抬起头望向门口，中景」
B. 每个分镜画内人物不超过 2 个；需要多人同框时用远景剪影表达，或拆成多镜
C. 每个分镜台词不超过 2 句、单句不超过 15 字；更长的内容拆镜
D. 同场景的连续分镜用景别递进（全景→中景→特写）制造节奏，不要每镜都跳场景
E. 每个 prompt_en 必须包含一句光照/氛围描述；同一场景的所有分镜逐字复用同一句（如 "moonlight through the broken window, cold blue-gray tone"）——防止同场景色彩漂移

输出 JSON 格式：
{{
  "shots": [
    {{
      "shot_index": 1,
      "scene_desc": "画面描述",
      "characters": ["角色名"],
      "action": "动作描述（含每个角色的位置姿态，只用常见动作）",
      "camera": "景别+运镜，如：中景 推",
      "dialogue": "中文对话内容（如有，≤2句）",
      "prompt_en": "Detailed English prompt for AI video generation. MUST include: full appearance of every character, shot-size and camera-movement phrases, each character's position state, the shared lighting sentence for this scene. Natural scene only, NO design sheet or three-view layout."
    }}
  ]
}}"""


def review_system_prompt():
    """分镜自审修复清单（便宜的一次调用，省下游贵的生成）"""
    return """你是 AI 视频生成适配审校。下面是一份分镜 JSON（shots 数组）。
逐条检查并直接修复以下问题：
1. 精确物理交互（拿起特定物品、递给、系扣、抓腕）→ 改成状态描述，或拆成两个简单动作镜头
2. 单镜画内超过 2 个角色 → 拆镜，或改为远景剪影
3. 单镜台词超过 2 句或单句超过 15 字 → 拆镜或精简
4. 不可外化的内心活动（意识到、想起、感到、明白了）→ 改成可见动作或表情特写
5. 相邻分镜人物位置状态不连续（上一镜上船、下一镜在岸）→ 修正为连续状态
6. 同场景分镜缺少统一光照句 → 补上，且同场景各镜逐字一致
7. prompt_en 缺少景别/运镜英文短语 → 按该镜 camera 字段补入
8. 保留原有规则：每个角色的完整外观必须在每个出现的 prompt_en 里；对话字幕用中文并写明 "Chinese subtitle"
只输出修订后的完整 JSON（格式 {"shots": [...]}，shot_index 从 1 连续重排），不要任何解释文字。"""


def assets_system_prompt():
    return """请严格按照以下要求执行：

1. 首先仔细通读并深度理解输入的全部文本内容；

2. 从文本中精准提取角色、场景、道具三类画面提示词，全程固定纯白色纯色背景，不添加任何背景元素；

3. 【角色提取强制要求】需完整拆解并提取每一位角色的全套细节。注意角色可能是不同类型，请按其本质提取：
   - 人类角色：年龄特征、外貌特征（五官、脸型、肤色、神态、身材体态）、发型细节（款式、发色、发长、发饰）、服饰全套细节（形制、款式、颜色、面料、纹样、配饰、鞋履等）
   - 动物角色：物种、毛色/羽色、体型大小、身体比例、特殊标记（如斑点、条纹）、眼睛颜色、耳朵形状、尾巴形态等
   - 植物角色：植物种类、整体颜色、大小尺寸、形态特征（叶片形状、花瓣数量、枝干粗细）、生长状态（茂盛、蓑萎、开花、结果）、表面质感等
   - 非生物角色：材质（金属、石头、布料、水滴等）、颜色、形状、大小尺寸、表面质感（光滑、粗糙、透明）、特殊特征等

4. 【场景提取要求】仅提取文本中明确提及的场景核心元素，场景描述词；
   - 每个场景必须给出 3~5 个「一致性锚点」：可画、可认、可核对的具体物件（如"补丁船篷"、"断裂的第七块桥板"、"绿锈铜铃"），写明位置与特征——「陈旧的氛围」「岁月的痕迹」这类没法核对的形容词不是锚点，观众靠锚点认出"又回到这里了"
   - 写明主要光照状态（日/黄昏/夜 + 光源方向与色温），以文本中实际出现的时段为准，不要凭空补全家桶

5. 【道具提取要求】精准提取文本中出现的所有手持/摆放/随身道具，包含道具样式、材质、颜色、细节特征；
   - 每个道具必须标注尺度参照（handheld scale 手持级 / furniture scale 家具级 / architecture scale 建筑级）——不写尺度，皮箱会被画成衣柜
   - 船、马车、宅门这类"会入画的大资产"也要当道具提取，否则每帧都会发明一个全新的

6. 输出格式清晰分类：分「角色画面提示词」「场景画面提示词」「道具画面提示词」三大板块，角色需按单人逐条拆分，细节完整不遗漏、不篡改、不脑补文本外信息，语言为精准画面描述词，适配AIGC生成逻辑。

必须严格输出 JSON 格式：
{{  "characters": [{"name": "角色名", "desc": "详细的中文视觉特征描述，根据角色类型包含相应的外观细节，纯白色背景", "prompt_en": "Detailed English visual description for AI image generation, white background, character design sheet, three views, no text or names in image"}],
  "scenes": [{"name": "场景名", "desc": "详细的中文场景视觉描述，含3~5个具体锚点物件与光照状态，纯白色背景", "prompt_en": "Detailed English scene visual description for AI image generation, white background, include 3-5 concrete recognizable anchor objects with positions, lighting state specified, absolutely no people anywhere"}],
  "props": [{"name": "道具名", "desc": "详细的中文道具视觉描述，包含样式、材质、颜色、细节特征与尺度，纯白色背景", "prompt_en": "Detailed English prop visual description for AI image generation, including style, material, color, details, scale reference (e.g. handheld scale), pure white background, no people, no hands"}]
}

注意：
- 每个角色必须单独拆分，不要合并
- `desc` 字段必须用中文描述，方便用户阅读和编辑
- `prompt_en` 字段必须用英文描述，适合AI图像生成
- 每个 prompt_en 末尾加上 "white background, character design sheet, three views"；场景加 "absolutely no people anywhere"；道具加 "pure white background, no people, no hands"
- 不要遗漏任何角色、场景或道具"""


# 内容安全敏感词列表（用于图片/视频 prompt 清洗）
_CONTENT_POLICY_WORDS = [
    'violence', 'violent', 'bloody', 'blood', 'gore', 'murder', 'kill', 'killing',
    'weapon', 'gun', 'knife', 'sword', 'bomb', 'explosion', 'shoot', 'shooting',
    'nude', 'naked', 'sexual', 'porn', 'erotic', 'drug', 'alcohol abuse',
    'torture', 'suicide', 'self-harm', 'racist', 'discrimination',
    'wound', 'wounded', 'bleeding', 'corpse', 'death', 'dead body',
    'abuse', 'assault', 'battle', 'war', 'fight', 'fighting',
    '暴力', '血腥', '杀戮', '武器', '枪支', '色情', '毒品',
    '流血', '尸体', '撕咬', '皮开肉绽', '浑身是血', '血泊',
    '撕下一块皮肉', '咬住', '伤口', '鞭打', '虐待',
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


def sanitize_image_prompt(prompt):
    """清洗图片 prompt，移除可能触发内容安全策略的关键词"""
    prompt_lower = prompt.lower()
    cleaned = prompt
    for word in _CONTENT_POLICY_WORDS:
        if word.lower() in prompt_lower:
            cleaned = cleaned.replace(word, '').replace(word.lower(), '').replace(word.title(), '')
    # 清理多余空格
    cleaned = ' '.join(cleaned.split())
    return cleaned


# 景别/运镜中文词 → 英文短语（借鉴 shuohao size-phrase/camera-phrase：词必须进提示词，不赌模型自选）
_CAMERA_EN = [
    ('大远景', 'extreme wide shot'), ('远景', 'wide establishing shot'), ('全景', 'wide shot'),
    ('中景', 'medium shot'), ('近景', 'medium close-up'), ('大特写', 'extreme close-up'), ('特写', 'close-up'),
    ('跟拍', 'tracking shot'), ('手持', 'handheld camera'),
    ('推', 'slow push in'), ('拉', 'pull out'), ('摇', 'pan'), ('固定', 'static shot'),
]


def camera_phrase(camera):
    c = (camera or '').strip()
    hits = [en for zh, en in _CAMERA_EN if zh in c]
    return ', '.join(dict.fromkeys(hits))


def build_video_prompt(shot, shot_assets):
    """根据分镜和参考素材构建视频生成 prompt（强调角色外观一致性）
    
    Returns:
        (english_prompt, chinese_prompt) 元组
    """
    base_prompt = shot.get('prompt_en', '') or shot.get('scene_desc', '')
    scene_desc_cn = shot.get('scene_desc', '')
    cam_en = camera_phrase(shot.get('camera'))
    if cam_en:
        base_prompt = f"{base_prompt}. Shot framing and camera movement: {cam_en}."
    
    # 【重要】禁止视频模型生成任何文字/字幕，中文字幕由 ffmpeg 后期烧录
    en_prompt = "No text, no subtitles, no captions, no labels, no written words, no letters, no signs, no watermarks, no typography, no writing of any kind should appear anywhere in the video. Pure cinematic scene only. "
    
    # 【角色一致性】在提示词开头强调必须严格匹配参考图
    if shot_assets:
        char_names = [a.get('name', '') for a in shot_assets if a.get('category') == 'characters']
        if char_names:
            en_prompt += f"STRICT CHARACTER CONSISTENCY REQUIRED: All characters ({', '.join(char_names)}) MUST appear exactly as shown in the reference images. Their facial features, hairstyle, hair color, skin tone, body proportions, clothing style and colors must match the reference images PRECISELY. Do NOT redesign, reinterpret, or alter any character's appearance in any way. "
    
    en_prompt += base_prompt
    
    # 中文提示词（供前端展示）
    cn_prompt = scene_desc_cn or base_prompt
    
    if shot_assets:
        char_descs = []
        scene_descs = []
        prop_descs = []
        char_descs_cn = []
        scene_descs_cn = []
        prop_descs_cn = []
        for a in shot_assets:
            desc = a.get('desc', '')
            desc_cn = a.get('desc_cn', '') or a.get('desc', '')
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
                char_descs_cn.append(f"{name}: {desc_cn}")
                # 【面部一致性】强调面部特征和整体外观
                en_prompt += f" CRITICAL for {name}: Face (face shape, eye shape and color, nose shape, mouth, eyebrows, skin tone), hair (style, color, length), body (height, build, proportions), and clothing (style, color, pattern) MUST EXACTLY match the reference image. Even minor deviations are NOT acceptable."
            elif cat == 'scenes':
                scene_descs.append(desc)
                scene_descs_cn.append(desc_cn)
            elif cat == 'props':
                prop_descs.append(desc)
                prop_descs_cn.append(desc_cn)
        
        consistency_parts = []
        consistency_parts_cn = []
        if char_descs:
            consistency_parts.append("CHARACTER REFERENCE (appearance MUST match reference images exactly): " + "; ".join(char_descs))
            consistency_parts_cn.append("角色参考(外观必须严格匹配参考图): " + "; ".join(char_descs_cn))
        if prop_descs:
            consistency_parts.append("Props: " + "; ".join(prop_descs))
            consistency_parts_cn.append("道具: " + "; ".join(prop_descs_cn))
        if scene_descs:
            consistency_parts.append("Scene: " + "; ".join(scene_descs))
            consistency_parts_cn.append("场景: " + "; ".join(scene_descs_cn))
        
        if consistency_parts:
            en_prompt = f"{en_prompt}. {' | '.join(consistency_parts)}. Use reference images ONLY for character appearance consistency, NOT as the starting frame."
            cn_prompt = f"{cn_prompt}. {' | '.join(consistency_parts_cn)}"
    
    en_prompt = f"{en_prompt}. The video MUST begin directly with the described natural cinematic scene. Never show any design sheet, character layout, three-view orthographic, or reference board in the video. Start immediately with the actual story scene."
    en_prompt = sanitize_video_prompt(en_prompt)
    
    return en_prompt, cn_prompt


def is_mostly_chinese(text):
    """检测文本是否主要为中文"""
    if not text:
        return False
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return chinese_chars > len(text) * 0.3


def translate_cn_to_en(text, api_key, model=None):
    """将中文提示词翻译为英文（用于发送给视频模型）"""
    if not text or not is_mostly_chinese(text):
        return text  # 已经是英文，直接返回
    try:
        from ..config import get_vendor_api_key, get_vendor_base_url, get_vendor_from_model
        from ..models import DEFAULT_TEXT_MODEL
        model = model or DEFAULT_TEXT_MODEL
        base_url = get_vendor_base_url(model)
        is_ollama = get_vendor_from_model(model) == 'ollama'
        key = api_key or get_vendor_api_key(model)
        headers = {'Content-Type': 'application/json'}
        if not is_ollama:
            headers['Authorization'] = f'Bearer {key}'
        payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': 'You are a professional translator. Translate the following Chinese video scene description into English. Keep it vivid and cinematic. Output ONLY the English translation, nothing else.'},
                {'role': 'user', 'content': text}
            ],
            'max_tokens': 1024,
            'temperature': 0.3
        }
        import requests
        resp = requests.post(f'{base_url}/chat/completions', headers=headers, json=payload, timeout=120 if is_ollama else 60)
        if resp.status_code == 200:
            result = resp.json()
            translated = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            if translated:
                print(f"[翻译] 中文→英文: {text[:50]}... → {translated[:50]}...")
                return translated
    except Exception as e:
        print(f"[翻译] 翻译失败，使用原文: {e}")
    return text
