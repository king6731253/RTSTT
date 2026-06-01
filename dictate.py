# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "google-genai",
# ]
# ///

from google import genai
from google.genai import types
import sys
import os
import mimetypes
import re

# 强制将标准输出和错误输出重定向为 UTF-8 编码，防止在部分非交互式 Shell 或 ASCII 终端下输出中文报错
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

if len(sys.argv) < 2:
    print("用法: dictate.py <音频文件路径>")
    sys.exit(1)

audio_path = os.path.abspath(sys.argv[1])
if not os.path.exists(audio_path):
    print(f"错误: 找不到音频文件 {audio_path}", file=sys.stderr)
    sys.exit(1)

# 获取 API Key，优先从环境变量读取，其次使用默认硬编码 Key
api_key = os.environ.get("GEMINI_API_KEY", "AIzaSyC93bGTPtHR_g3UcGBf6G9Ful8uL33KAt0")
client = genai.Client(api_key=api_key)

def clean_transcription_spaces(text: str) -> str:
    """
    智能文本后处理：
    1. 移除所有汉字与汉字之间的冗余空格（因说话停顿导致）。
    2. 移除汉字与中文标点、中文标点之间的所有多余空格。
    3. 缩减英文单词之间的多重积压空格为单空格，保留中英交界处的合理空格。
    """
    # 常用中文字符区间
    hz_pattern = r'[\u4e00-\u9fa5]'
    # 常用中文标点符号（包括全角标点）
    zh_punc = r'，。？！、：；“”‘’（）《》【】——……'
    
    # 1. 移除汉字与汉字之间的空格
    text = re.sub(r'(' + hz_pattern + r')\s+(' + hz_pattern + r')', r'\1\2', text)
    
    # 2. 移除汉字与中文标点之间的空格
    text = re.sub(r'(' + hz_pattern + r')\s+([' + zh_punc + r'])', r'\1\2', text)
    text = re.sub(r'([' + zh_punc + r'])\s+(' + hz_pattern + r')', r'\1\2', text)
    
    # 3. 移除中文标点之间的空格
    text = re.sub(r'([' + zh_punc + r'])\s+([' + zh_punc + r'])', r'\1\2', text)
    
    # 4. 将连续的多个空格合并为单个空格（保留英文单词间正常的单空格）
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

with open(audio_path, "rb") as f:
    audio_bytes = f.read()

mime_type, _ = mimetypes.guess_type(audio_path)
if not mime_type:
    # Fallback to mp4/m4a container
    mime_type = "audio/mp4"

# 针对“逐字听写、去除空格、智能代词区分、智能标点全半角、粤语原生支持”深度定制的 Prompt
prompt = """
你是一个极其精准的、逐字逐句的语音听写输入助手。

你的核心职责是：【原汁原味、字字对应地转录语音，绝对不允许进行任何词汇替换、语病修改或语义润色。】

具体规则要求：
1. **逐字原样转录**：用户怎么说，你就怎么写。绝对不要对句子进行“润色”、“语病修正”、“词语替换”或“同义词转换”。
2. **完整保留口语与重复**：
   - 必须原封不动地保留口语化的语气词（如普通话的：啊、呢、哈、哦、啦、吧 等；以及粤语特有的：呀、啦、呢、啫、嗰、喎、嘅、咩、嘛、啵 等）。
   - 必须完整保留说话人的“重复、口吃、结巴、迟疑”词汇。例如：如果用户连续说“怎么样，怎么样，怎么样”，你必须完整输出“怎么样，怎么样，怎么样”，绝对不能做合并或删减！
3. **多语言与技术术语**：高精度支持中英文、缩写、技术术语和多语言混杂（如“用 Python 跑 API 接口”），保持原本的英文拼写或缩写。
4. **添加自然标点**：仅根据自然的语气停顿，添加最基础的标点符号。
5. **绝对零对话废话**：输出的内容必须只有听写出来的字词，绝对不能包含任何解释、自我介绍、说明或多余对话。
6. **严禁中文内空格**：汉字与汉字之间、汉字与中文标点符号之间绝对不能有任何空格。只在英文单词之间保留正常空格。
7. **精准同音字与代词区分（他/她/它）**：
   必须根据整句话的【上下文语义逻辑】进行智能推理，精准选择最正确的第三人称代词，严禁千篇一律地全写成“他”：
   - **“它”**：当语境明确指向无生命物体、概念、软件、系统、设备、动物、API 或具体工具时使用。
   - **“她”**：当语境明确指向女性角色（如：妈妈、女同事、女名、姐姐等）时使用。
   - **“他”**：仅在语境明确指向男性角色、泛指人类或性别不详时使用。
8. **智能标点符号选择（全角/半角）**：
   必须根据标点符号【前后的语言环境】智能且精准地选择全角（中文）或半角（英文）标点，严禁一刀切：
   - **中文全角标点（，。？！：）**：用于中文汉字之间、汉字之后。
   - **英文半角标点（, . ? ! :）**：用于纯英文句子中，或紧跟在英文单词、代码、技术术语、文件名、网址之后（如 `test.wav`）。
9. **粤语（广东话/廣東話）原生与混杂的高精度字字对应转录**：
   你必须能够完美识别并转录【粤语、粤英混杂、粤普混杂】的语音输入：
   - **原汁原味输出粤语字（核心规则）**：当用户以粤语发音输入时，请【百分之百字字对应地输出粤语白话字/口语字】（例如使用：哋、喺、咗、嘢、唔、乜、冇、佢、系、咁、靓、搵、睇 等），绝对不要将其翻译或转换为普通话或中文书面语！
   - **严禁纠正语法或调整语序**：粤语的特殊句式、口语词汇、倒装语序等必须**原封不动地保留**，绝对不能因为“听起来不符合普通话语法习惯”而对语序或词汇进行订正，确保原汁原味、字字对应！
   - *具体原样转录范例*：
     - 用户说 “我哋喺度开紧会” ➡️ 必须输出为 “我哋喺度开紧会” （绝对不要改写或翻译）
     - 用户说 “唔好意思，我迟咗” ➡️ 必须输出为 “唔好意思，我迟咗” （绝对不要改写或翻译）
     - 用户说 “你讲乜嘢呀” ➡️ 必须输出为 “你讲乜嘢呀” （绝对不要改写或翻译）
     - 用户说 “真系唔该晒你” ➡️ 必须输出为 “真系唔该晒你” （绝对不要改写或翻译）
   - **粤英夹杂处理**：保留原本说出的英文或口语习惯（如说“Send个Email”就直接输出“Send个Email”），不需要翻译成中文。
"""

try:
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=types.Part.from_bytes(
            data=audio_bytes,
            mime_type=mime_type
        ),
        config=types.GenerateContentConfig(
            system_instruction=prompt,
            temperature=0.0,
        )
    )
    
    # 提取转写文本，安全处理 NoneType
    raw_text = response.text or ""
    raw_text = raw_text.strip()
    
    # 过滤掉仅含时间戳/方括号的无意义静音响应（如 [ 0m0s - 0m3s ]）
    if not raw_text or re.match(r'^[\s\d\-ms\[\]\.:]+$', raw_text):
        cleaned_text = ""
    else:
        # 通过智能算法过滤掉因说话停顿产生的冗余中文空格，保留英文正常空格
        cleaned_text = clean_transcription_spaces(raw_text)
    
    # 输出干净无空格干扰的转写文本
    print(cleaned_text)
except Exception as e:
    print(f"错误: {e}", file=sys.stderr)
    sys.exit(1)
