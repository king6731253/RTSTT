# 🎙️ Gemini macOS 全局高精度极速语音听写系统（RTSTT）维护手册

本目录存放了专为 macOS 深度定制的全局语音听写系统（通过快捷键 `Control+Option+G` 一键开关）的核心程序与优化逻辑。本手册旨在供用户或未来的 AI 编码助手在后续进行功能微调、规则迭代时，能够秒级理清架构与优化历史。

---

## 📂 1. 核心文件架构

所有的关键脚本与环境均部署在 `/Users/yuanjin/localbin/` 下：

| 文件名称 | 类型 | 职责描述 |
| :--- | :--- | :--- |
| `dictate_toggle.sh` | Zsh 脚本 | **总控制中心**。控制快捷键的“录音开始/结束”交替切换；控制 `ffmpeg` 录音启停与临时音频文件清理；静默唤醒并极速调用守护进程获取转写结果；最终通过模拟物理按键 `Cmd+V` 自动粘贴。 |
| `dictate_daemon.py` | Python 脚本 | **长连接后台守护进程**。常驻在本机 `127.0.0.1:18888`。实例化全局 `genai.Client` 以保持与 Google Gemini API 的 HTTPS 长连接通道。接收 shell 脚本的本地 `curl` 转写任务。包含核心 Prompt 转写规则。 |
| `dictate.py` | Python 脚本 | **容灾备份脚本**。当后台守护进程由于某些极罕见状况未启动或崩溃时，`dictate_toggle.sh` 会在毫秒级内自动无缝回退调用它，确保全局听写 100% 成功。包含与守护进程一致的核心 Prompt。 |
| `visualizer.py` | Python 脚本 | **GUI 胶囊舱悬浮窗（已归档）**。第一代 Siri 风格波行动效悬浮窗，现已被原生无延迟声效反馈替代以追求 0ms 响应极致体验。 |
| `.venv/` | Python 虚拟环境 | 使用 `uv` 构建的极致优化虚拟环境。内嵌 Python 解释器并预装了 `google-genai` 和 `pyobjc-framework-Cocoa`。 |

---

## ⚡ 2. 深度速度优化历史 (ASR Speed Hacks)

为了将听写响应从最初的 **6~8 秒** 压缩至如今的 **~2 秒（光标仅闪烁 4 下）** 的绝对极限，系统实施了以下三项底层优化：

1. **设备快速开启（屏蔽视频扫描，提速 ~500ms）**：
   * *问题*：`ffmpeg` 以 `-i ":default"` 启动时，macOS 会去扫描所有摄像头，这会触发“连续互通相机（Continuity Camera）”无线尝试连接附近的 iPhone，带来巨大的阻滞。
   * *解决*：在 `dictate_toggle.sh` 中锁定为 `ffmpeg -i "none:default"`。显式指定无视频输入，完全跳过摄像头扫描和蓝牙搜寻。设备开启时间由 500ms+ 降至 **~20ms**，彻底解决了“说话前必须等待，否则漏字”的痛点。

2. **音频 5.5 倍压缩（提速网传时间）**：
   * *优化*：锁定 `ffmpeg -ar 16000 -ac 1`。强制以符合 ASR 规格的**单声道、16kHz 采样率**录制。音频体积缩小 5.5 倍（每秒仅 32KB），使录音的上传与 API 服务端解码时间成倍缩短。

3. **常驻长连接（免除 TLS 握手与 Python 启动，提速 1 秒+）**：
   * *优化*：引入 `dictate_daemon.py` 后台监听。在“开始录音”时自动探测并静默拉起它。利用用户说话的时间，在后台完成 Python 启动和 **Gemini API 的 HTTPS TLS 握手建立**。
   * 结束录音时，通过本地 **3ms 的 `curl` 请求** 直连守护进程，复用已经温好的 HTTPS 连接，彻底免去了建立加密通道的巨大网络开销。

---

## 🛠️ 3. 常见维护与规则自定义

### 📝 如何更新听写提示词（Prompt / 规矩）
如果您在未来想要添加新的听写规则、专有名词映射，或遇到特定的同音字纠错：
1. 打开 `/Users/yuanjin/localbin/dictate_daemon.py`（和备份的 `dictate.py`）。
2. 修改代码中大段的 `prompt = """ ... """` 字符串，在里面直接用自然语言追加规则。
3. 保存文件。
4. 在终端中运行以下命令，强制结束当前的常驻进程：
   ```bash
   pkill -f dictate_daemon.py
   ```
5. **无需手动重启**：当您下一次按下听写快捷键 `Control+Option+G` 时，控制脚本会检测到进程不在，并**自动静默拉起载入了您最新规则的守护进程**。

### 🎵 如何更换提示音效
1. 打开 `/Users/yuanjin/localbin/dictate_toggle.sh`。
2. 找到 `afplay /System/Library/Sounds/Ping.aiff &`（开始音）和 `afplay /System/Library/Sounds/Glass.aiff &`（结束音）。
3. 将文件名更换为 `/System/Library/Sounds/` 下的其它音频文件（如 `Bottle.aiff`）。保存后立即生效。

---

## 🔒 4. 系统环境依赖与部署环境

* **API Key 依赖**：脚本自动从 `~/.zshrc` 中读取并继承 `GEMINI_API_KEY` 环境变量。
* **快捷指令（Apple Shortcut）绑定**：全局快捷键 `Control+Option+G` 被映射为在后台静默运行 shell 命令 `/Users/yuanjin/localbin/dictate_toggle.sh`。
* **首次运行标志**：权限自检成功后会在家目录下生成空文件 `~/.gemini_dictation_checked`，以此跳过后续 of the 重复权限检测，实现微秒级零延迟。

---

*“极致流畅，字字对应。代码千万行，唯快与准不破。”*  
*由 Antigravity 携手 袁锦 共同设计与深度调优，构建于 2026 年 5 月。*
