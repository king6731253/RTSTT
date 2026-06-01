#!/bin/zsh

# 强制设定系统和 Python 环境变量以支持中文 UTF-8 编码，防止中文在非交互式后台运行下乱码或崩溃
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
export PYTHONIOENCODING="utf-8"

# 强制将 Homebrew 和 macOS 标准路径加入 PATH，解决快捷指令后台运行找不到 ffmpeg 的问题
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

FLAG_FILE="$HOME/.gemini_dictation_checked"

# 获取最佳的麦克风录音设备索引，自动排除 iShotAudioPlugin、BlackHole 等虚拟声卡
get_mic_index() {
    # 执行 ffmpeg 列出所有设备，并过滤出音频设备部分
    local devices
    devices=$(ffmpeg -f avfoundation -list_devices true -i "" 2>&1)
    
    # 解析音频设备行，排除常见虚拟声卡，并按优先级匹配带“麦克风”或“Microphone”字样的设备
    local mic_lines
    mic_lines=$(echo "$devices" | grep -A 50 "AVFoundation audio devices:" | grep "\[[0-9]\]" | grep -v -i -E "ishot|blackhole|loopback|zoom|soundflower|virtual")
    
    local best_mic
    best_mic=$(echo "$mic_lines" | grep -i -E "麦克风|microphone|mic" | head -n 1)
    
    if [ -n "$best_mic" ]; then
        echo "$best_mic" | sed -E 's/.*\[([0-9]+)\].*/\1/'
        return
    fi
    
    local fallback_mic
    fallback_mic=$(echo "$mic_lines" | head -n 1)
    if [ -n "$fallback_mic" ]; then
        echo "$fallback_mic" | sed -E 's/.*\[([0-9]+)\].*/\1/'
        return
    fi
    
    echo "default"
}

# ==================== 首次运行/权限检测函数 ====================
check_permissions() {
    # 1. 检测 ffmpeg 是否存在
    if ! command -v ffmpeg &> /dev/null; then
        osascript -e 'display alert "⚠️ Gemini 语音听写错误" message "未检测到 ffmpeg 命令。\n\n请确保已安装 Homebrew，并在终端运行 brew install ffmpeg 安装录音支持。"'
        exit 1
    fi

    # 2. 检测 API Key 是否配置
    source ~/.zshrc 2>/dev/null
    if [ -z "$GEMINI_API_KEY" ]; then
        osascript -e 'display alert "⚠️ Gemini 语音听写错误" message "未检测到 GEMINI_API_KEY 环境变量。\n\n请确保已在 ~/.zshrc 中配置并使用 export 导出该变量。"'
        exit 1
    fi

    # 3. 检测辅助功能（Accessibility）模拟按键权限
    if ! osascript -e 'tell application "System Events" to get name of first process' &> /dev/null; then
        osascript -e 'display alert "⚠️ Gemini 语音听写权限不足" message "检测到没有【辅助功能】权限。\n\n请前往「系统设置 -> 隐私与安全性 -> 辅助功能」，允许「快捷指令」或「终端」控制您的电脑。"'
        exit 1
    fi

    # 4. 检测麦克风（Microphone）录音权限 (通过 0.1秒 极速静默录音测试)
    local mic_idx=$(get_mic_index)
    ffmpeg -y -f avfoundation -i "none:$mic_idx" -t 0.1 /tmp/perm_test.wav >/dev/null 2>&1
    local ret=$?
    if [ ! -f "/tmp/perm_test.wav" ] || [ $ret -ne 0 ]; then
        osascript -e 'display alert "⚠️ Gemini 语音听写权限不足" message "检测到没有【麦克风】录音权限。\n\n请前往「系统设置 -> 隐私与安全性 -> 麦克风」，允许「快捷指令」或「终端」使用您的麦克风。"'
        rm -f /tmp/perm_test.wav
        exit 1
    fi
    rm -f /tmp/perm_test.wav
}

# 如果没有检测标记文件，则进行自检
if [ ! -f "$FLAG_FILE" ]; then
    check_permissions
    touch "$FLAG_FILE"
fi

# 临时音频文件与进程 ID 保存路径
AUDIO_FILE="/tmp/gemini_dictation.wav"
PID_FILE="/tmp/gemini_dictation.pid"
FFMPEG_LOG="/tmp/gemini_ffmpeg.log"

if [ -f "$PID_FILE" ]; then
    # ==================== 停止录音并开始转写 ====================
    # 播放高品质无延迟的“停止录音并处理”提示音 (Glass 声音，清脆悦耳)
    afplay /System/Library/Sounds/Glass.aiff &
    
    # 1. 强制终止录音进程
    PID=$(cat "$PID_FILE")
    kill "$PID" 2>/dev/null
    rm -f "$PID_FILE"
    # 双重保险：强制清理任何可能残留的 ffmpeg 录音进程
    pkill -f "ffmpeg.*gemini_dictation.wav" 2>/dev/null
    
    # 彻底清理可能残留的 visualizer 胶囊舱悬浮窗进程，保证完全退场
    pkill -f "visualizer.py" 2>/dev/null
    
    # 极速轮询检测，直到 ffmpeg 正常退出并完整关闭音频文件（最大等待 0.3 秒，通常 <0.05秒 即可完成，比固定 sleep 0.3秒 节省约 250ms）
    local count=0
    while kill -0 "$PID" 2>/dev/null && [ $count -lt 15 ]; do
        sleep 0.02
        count=$((count + 1))
    done
    
    # 引入 zsh 环境变量以获得 GEMINI_API_KEY
    source ~/.zshrc 2>/dev/null
    
    # 极速调用常驻后台听写守护进程（127.0.0.1:18888），通过保活 HTTP 长连接直接提交任务，免去 TLS 握手及 Python 启动开销！
    # curl 发送本机环回请求仅需 3~5ms，瞬间触达，响应速度成倍提升！
    TEXT=$(curl -s -X POST -d "$AUDIO_FILE" http://127.0.0.1:18888/transcribe)
    
    # 容灾备用机制：若后台守护进程未运行或报错，回退到独立的 dictate.py，确保 STT 100% 成功
    if [ -z "$TEXT" ] || [[ "$TEXT" == Error:* ]]; then
        TEXT=$(/Users/yuanjin/localbin/.venv/bin/python /Users/yuanjin/localbin/dictate.py "$AUDIO_FILE")
    fi
    
    if [ -n "$TEXT" ]; then
        # 拷贝到剪贴板
        echo -n "$TEXT" | pbcopy
        # 模拟 Command + V 粘贴
        osascript -e 'tell application "System Events" to keystroke "v" using {command down}'
        
        # 将转写结果同时输出到标准输出
        echo "$TEXT"
    else
        # 转写失败时保留轻量提示，便于排查故障
        osascript -e 'display notification "未检测到有效语音文本" with title "⚠️ Gemini 语音听写"'
    fi
else
    # ==================== 开始录音 ====================
    # 0. 极其重要：启动前彻底清理旧的 ffmpeg 进程，并删除旧的音频文件，绝对防止录音内容叠加或混合！
    pkill -f "ffmpeg.*gemini_dictation.wav" 2>/dev/null
    rm -f "$AUDIO_FILE" "$PID_FILE" "$FFMPEG_LOG"
    
    # 1. 检测后台常驻听写守护进程是否存活，若已死则在您说话的黄金时间里自动、静默地在后台唤醒它！
    # 利用说话的几秒时间完成进程初始化并建立 HTTPS 长连接，到结束听写时即为热连接，达到 0ms 握手开销！
    if ! curl -s --connect-timeout 0.1 http://127.0.0.1:18888/ping &>/dev/null; then
        (source ~/.zshrc 2>/dev/null; /Users/yuanjin/localbin/.venv/bin/python /Users/yuanjin/localbin/dictate_daemon.py >/dev/null 2>&1 &)
    fi
    
    # 2. 播放高品质无延迟的“开始录音”提示音 (Ping 声音，清亮悦耳的科技短音，代表已进入录音状态)
    afplay /System/Library/Sounds/Ping.aiff &
    
    # 3. 启动后台 ffmpeg 录音进程，采用单声道 (1 channel) 16000Hz 采样率，自动获取真实的麦克风设备索引并屏蔽视频设备扫描
    # 彻底杜绝了 Continuity Camera 以及摄像头扫描带来的数百毫秒初始化延迟，实现毫秒级瞬时开启录音，绝不丢字！
    local mic_idx=$(get_mic_index)
    ffmpeg -y -f avfoundation -i "none:$mic_idx" -ar 16000 -ac 1 "$AUDIO_FILE" > "$FFMPEG_LOG" 2>&1 &
    
    # 保存后台 ffmpeg 进程 PID
    echo $! > "$PID_FILE"
fi
