# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "google-genai",
# ]
# ///

import os
import sys
import mimetypes
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from google import genai
from google.genai import types

# 强行设定标准输出为 UTF-8 防止中文乱码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# 获取 API Key，实例化全局持久性 Client 保持 HTTPS 长连接
api_key = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def clean_transcription_spaces(text: str) -> str:
    hz_pattern = r'[\u4e00-\u9fa5]'
    zh_punc = r'，。？！、：；“”‘’（）《》【】——……'
    text = re.sub(r'(' + hz_pattern + r')\s+(' + hz_pattern + r')', r'\1\2', text)
    text = re.sub(r'(' + hz_pattern + r')\s+([' + zh_punc + r'])', r'\1\2', text)
    text = re.sub(r'([' + zh_punc + r'])\s+(' + hz_pattern + r')', r'\1\2', text)
    text = re.sub(r'([' + zh_punc + r'])\s+([' + zh_punc + r'])', r'\1\2', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# 极致调优的字字对应提示词
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

class DictateHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # 禁用烦人的 HTTP 日志，专注速度与清洁
        return

    def do_GET(self):
        if self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'pong')
            return
        self.send_error(404)

    def do_POST(self):
        if self.path == '/transcribe':
            content_length = int(self.headers['Content-Length'])
            audio_path = self.rfile.read(content_length).decode('utf-8').strip()
            
            if not os.path.exists(audio_path):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Error: Audio file not found')
                return
                
            try:
                with open(audio_path, "rb") as f:
                    audio_bytes = f.read()
                    
                mime_type, _ = mimetypes.guess_type(audio_path)
                if not mime_type:
                    mime_type = "audio/mp4"
                    
                # 使用全局持久化的 client 发送请求，共享连接池，跳过 TCP/SSL 握手
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
                    cleaned_text = clean_transcription_spaces(raw_text)
                
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(cleaned_text.encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error: {e}".encode('utf-8'))
            return
        self.send_error(404)

def run():
    server_address = ('127.0.0.1', 18888)
    httpd = HTTPServer(server_address, DictateHandler)
    # 优雅地常驻后台提供极速服务
    httpd.serve_forever()

if __name__ == '__main__':
    run()
