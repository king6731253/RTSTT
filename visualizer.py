# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyobjc-framework-Cocoa",
# ]
# ///

import tkinter as tk
import math
import random
import ctypes
from ctypes import cdll, c_double, Structure, c_void_p

class VoiceVisualizer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Gemini Dictation Visualizer")
        
        # 隐藏 macOS Dock 栏图标（必须在 tk.Tk() 初始化后调用，以防干扰 Tkinter 自身对 NSApplication 的特化定制导致崩溃）
        try:
            import AppKit
            # NSApplicationActivationPolicyAccessory = 1
            # 设定应用为“辅助/配件”类型，该类型支持完整显示浮动窗口，但绝不在 Dock 栏显示图标，亦不占用主菜单栏
            AppKit.NSApplication.sharedApplication().setActivationPolicy_(1)
        except Exception:
            pass
        
        # 1. 设为无边框、置顶、半透明（实现玻璃拟态感）
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        
        # 获取屏幕尺寸
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        self.width = 240
        self.height = 42
        
        # ==================== 智能定位逻辑：获取鼠标位置 ====================
        try:
            app_services = cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
            
            class CGPoint(Structure):
                _fields_ = [("x", c_double), ("y", c_double)]
                
            app_services.CGEventCreate.restype = c_void_p
            app_services.CGEventCreate.argtypes = [c_void_p]
            app_services.CGEventGetLocation.restype = CGPoint
            app_services.CGEventGetLocation.argtypes = [c_void_p]
            app_services.CFRelease.argtypes = [c_void_p]
            
            event = app_services.CGEventCreate(None)
            location = app_services.CGEventGetLocation(event)
            app_services.CFRelease(event)
            
            mx, my = location.x, location.y
        except Exception:
            mx, my = screen_width // 2, 100
            
        x = int(mx - self.width // 2)
        y = int(my + 20)
        
        if x < 10:
            x = 10
        elif x + self.width > screen_width - 10:
            x = screen_width - self.width - 10
            
        if y + self.height > screen_height - 30:
            y = int(my - self.height - 20)
            
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
        # ===================================================================
        
        # 设置窗口背景色
        self.bg_color = "#18181B"  
        self.root.configure(bg=self.bg_color)
        
        # 创建画布
        self.canvas = tk.Canvas(
            self.root, 
            width=self.width, 
            height=self.height, 
            bg=self.bg_color, 
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)
        
        # 初始化音频波动条数据
        self.num_bars = 16
        self.bar_width = 3
        self.bar_gap = 4
        self.max_bar_height = 24
        self.start_x = 90
        self.phase = 0.0
        
        # 绘制胶囊外壳与微标
        self.draw_capsule_shell()
        
        # ==================== 突破 macOS 全屏/多空间限制 ====================
        # 调用 macOS Cocoa 原生 API (PyObjC) 以赋予悬浮窗跨空间 (Spaces) 与在全屏应用上浮动的功能
        try:
            import AppKit
            # 获取当前 Tk 窗口在系统的 WindowNumber
            win_id = self.root.winfo_id()
            shared_app = AppKit.NSApplication.sharedApplication()
            nswindow = None
            
            # 通过 WindowNumber 匹配系统底层的 NSWindow 指针
            for w in shared_app.windows():
                if w.windowNumber() == win_id:
                    nswindow = w
                    break
            
            # 备用匹配方案：通过 Title 匹配
            if not nswindow:
                for w in shared_app.windows():
                    if w.title() == "Gemini Dictation Visualizer":
                        nswindow = w
                        break
            
            if nswindow:
                # 设定收集行为：
                # 1. NSWindowCollectionBehaviorCanJoinAllSpaces: 允许悬浮窗出现在所有 Space (包括全屏 App 的独立 Space)
                # 2. NSWindowCollectionBehaviorFullScreenAuxiliary: 强制允许悬浮窗以辅助面板层级漂浮在原生全屏 App 之上
                # 3. NSWindowCollectionBehaviorStationary: 切换 Space 时悬浮窗静止不动，不随动画滑动
                behavior = AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces | \
                           AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary | \
                           AppKit.NSWindowCollectionBehaviorStationary
                nswindow.setCollectionBehavior_(behavior)
                
                # 将窗口层级提升到状态栏/菜单栏层级 (NSStatusWindowLevel / 3)，使其能够彻底突破全屏 App 的图层遮挡
                nswindow.setLevel_(AppKit.NSStatusWindowLevel)
        except Exception as e:
            # 优雅捕获，若环境异常则使用基础 topmost 兜底
            print(f"macOS spaces optimization skipped: {e}")
        # ===================================================================
        
        # 开始动画循环
        self.animate()
        
    def draw_capsule_shell(self):
        r = 20
        self.canvas.create_arc(0, 0, r*2, self.height, start=90, extent=180, fill=self.bg_color, outline="")
        self.canvas.create_arc(self.width - r*2, 0, self.width, self.height, start=270, extent=180, fill=self.bg_color, outline="")
        self.canvas.create_rectangle(r, 0, self.width - r, self.height, fill=self.bg_color, outline="")
        
        self.canvas.create_oval(15, 17, 23, 25, fill="#30D158", outline="")  
        self.canvas.create_text(
            32, 21, 
            text="录音中...", 
            fill="#A1A1AA", 
            font=("SF Pro Text", 11, "bold"),
            anchor="w"
        )

    def animate(self):
        self.canvas.delete("wave_bar")
        self.phase += 0.15
        
        envelope = (math.sin(self.phase * 0.3) + math.cos(self.phase * 0.07)) / 2.0
        volume_factor = abs(envelope) * 0.7 + random.uniform(0.1, 0.3)
        
        for i in range(self.num_bars):
            offset = i * 0.4
            bar_factor = (math.sin(self.phase + offset) + 1.0) / 2.0
            bell_curve = math.sin((i / (self.num_bars - 1)) * math.pi)
            height = 3 + (bar_factor * self.max_bar_height * bell_curve * volume_factor)
            height = min(height, self.max_bar_height)
            
            x = self.start_x + i * (self.bar_width + self.bar_gap)
            y_center = self.height / 2
            y1 = y_center - height / 2
            y2 = y_center + height / 2
            
            if i < self.num_bars / 2:
                color = "#0A84FF"  
            else:
                color = "#BF5AF2"  
                
            self.canvas.create_line(
                x, y1, x, y2, 
                width=self.bar_width, 
                fill=color, 
                capstyle="round",
                tags="wave_bar"
            )
            
        self.root.after(30, self.animate)
        
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = VoiceVisualizer()
    app.run()
