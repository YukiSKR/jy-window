# -*- coding: utf-8 -*-
"""
极域屏幕广播窗口化工具 · v2.0（Canvas 自绘界面）
把极域学生端「屏幕广播」的全屏置顶无边框窗口，改成带标题栏、可拖动、
可最小化的普通窗口。

原理：纯 Win32 窗口样式操作（SetWindowLongPtr + SetWindowPos），
      不注入进程、不装驱动、不改极域任何文件。
界面：背景图 + 暗色面板 + 红色高亮 + 悬停/脉冲动效，全部 Canvas 自绘。
"""

import ctypes
import os
import sys
import time
import tkinter as tk
from ctypes import wintypes as wt

try:
    from PIL import Image, ImageDraw, ImageTk
except Exception:
    Image = None

APP_NAME = "极域广播 · 窗口化"
APP_VER = "2.0"

# ----------------------------------------------------------------- 配色
C_BG = "#08080C"
C_PANEL = "#12121A"
C_PANEL2 = "#0E0E14"
C_LINE = "#2C2C3A"
C_TEXT = "#F2F2F7"
C_SUB = "#8C8C9C"
C_ACCENT = "#E4122B"
C_ACCENT2 = "#FF3D5A"
C_OK = "#2BD98A"
C_WARN = "#FFB020"

# ----------------------------------------------------------------- Win32
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_POPUP = 0x80000000
WS_CHILD = 0x40000000
WS_EX_TOPMOST = 0x00000008
WS_EX_APPWINDOW = 0x00040000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040

HWND_TOPMOST = wt.HWND(-1)
HWND_NOTOPMOST = wt.HWND(-2)
SW_MINIMIZE = 6
SW_RESTORE = 9

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

if ctypes.sizeof(ctypes.c_void_p) == 8:
    _GetWindowLong = user32.GetWindowLongPtrW
    _SetWindowLong = user32.SetWindowLongPtrW
else:
    _GetWindowLong = user32.GetWindowLongW
    _SetWindowLong = user32.SetWindowLongW

_GetWindowLong.argtypes = [wt.HWND, ctypes.c_int]
_GetWindowLong.restype = ctypes.c_ssize_t
_SetWindowLong.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
_SetWindowLong.restype = ctypes.c_ssize_t

user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.EnumWindows.restype = wt.BOOL
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindowVisible.restype = wt.BOOL
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL
user32.IsIconic.argtypes = [wt.HWND]
user32.IsIconic.restype = wt.BOOL
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetWindowRect.restype = wt.BOOL
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, wt.UINT]
user32.SetWindowPos.restype = wt.BOOL
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.ShowWindow.restype = wt.BOOL
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int

kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                                ctypes.POINTER(wt.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wt.BOOL
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL

BLACKLIST_CLASS = {
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow", "ApplicationFrameWindow", "IME",
    "MSCTFIME UI",
}
KNOWN_CLASS_HINTS = ("broadcast", "elc", "deskmon", "screenrecv", "monitor")

DEFAULT_PROCESSES = ("studentmain.exe",)
TARGET_PROCESSES = set(DEFAULT_PROCESSES)


# ----------------------------------------------------------------- 工具
def res_path(*parts):
    cands = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        cands.append(os.path.join(base, *parts))
    here = os.path.dirname(os.path.abspath(__file__))
    cands.append(os.path.join(here, *parts))
    cands.append(os.path.join(here, os.pardir, *parts))
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]


def hex2rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb2hex(t):
    return "#%02X%02X%02X" % t


def lerp(c1, c2, t):
    a, b = hex2rgb(c1), hex2rgb(c2)
    t = max(0.0, min(1.0, t))
    return rgb2hex(tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))


def rrect(cv, x1, y1, x2, y2, r, **kw):
    """圆角矩形（平滑多边形实现）。"""
    return cv.create_polygon(
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        smooth=True, **kw)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_elevated(argv):
    try:
        script = os.path.abspath(sys.argv[0])
        params = " ".join(['"%s"' % script] + ['"%s"' % a for a in argv])
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1)
        return rc > 32
    except Exception:
        return False


def proc_name(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_title(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def screen_metrics():
    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    if w <= 0 or h <= 0:
        x = y = 0
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
    return x, y, w, h


def probe(hwnd):
    if not hwnd or not user32.IsWindow(hwnd):
        return None
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    r = wt.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    w, h = r.right - r.left, r.bottom - r.top
    vx, vy, vw, vh = screen_metrics()
    return {
        "hwnd": hwnd, "pid": pid.value, "proc": proc_name(pid.value),
        "cls": class_name(hwnd), "title": window_title(hwnd),
        "rect": (r.left, r.top, w, h),
        "ratio": (w * h) / float(vw * vh or 1),
        "iconic": bool(user32.IsIconic(hwnd)),
        "style": _GetWindowLong(hwnd, GWL_STYLE),
        "ex": _GetWindowLong(hwnd, GWL_EXSTYLE),
    }


def find_windows(processes, min_ratio=0.85, tracked=()):
    vx, vy, vw, vh = screen_metrics()
    v_area = float(vw * vh) or 1.0
    found = []
    tracked = set(tracked)

    def _cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wt.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return True
        if proc_name(pid.value) not in processes:
            return True
        cls = class_name(hwnd)
        if cls in BLACKLIST_CLASS:
            return True
        r = wt.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w <= 0 or h <= 0:
            return True
        style = _GetWindowLong(hwnd, GWL_STYLE)
        ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
        if style & WS_CHILD:
            return True

        ratio = (w * h) / v_area
        is_tracked = hwnd in tracked
        hint = any(k in cls.lower() for k in KNOWN_CLASS_HINTS)
        iconic = bool(user32.IsIconic(hwnd))
        if iconic and not is_tracked and not (min_ratio < 0.85 and hint):
            return True
        if ratio >= min_ratio or is_tracked or hint:
            found.append({
                "hwnd": hwnd, "pid": pid.value, "proc": proc_name(pid.value),
                "cls": cls, "title": window_title(hwnd),
                "rect": (r.left, r.top, w, h), "ratio": ratio,
                "iconic": iconic, "style": style, "ex": ex,
            })
        return True

    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return found


def to_window_mode(win, scale, minimize_after=False):
    hwnd = win["hwnd"]
    if not user32.IsWindow(hwnd):
        return False, "窗口已关闭"
    style = _GetWindowLong(hwnd, GWL_STYLE)
    ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
    new_style = (style | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX |
                 WS_THICKFRAME | WS_MAXIMIZEBOX) & ~WS_POPUP
    new_ex = (ex & ~WS_EX_TOPMOST) | WS_EX_APPWINDOW

    _SetWindowLong(hwnd, GWL_STYLE, new_style)
    _SetWindowLong(hwnd, GWL_EXSTYLE, new_ex)

    vx, vy, vw, vh = screen_metrics()
    s = scale if 0.3 <= scale <= 1.0 else 0.85
    w = int(vw * s)
    h = int(vh * s)
    x = vx + (vw - w) // 2
    y = vy + (vh - h) // 2

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    flags = SWP_FRAMECHANGED | SWP_NOACTIVATE
    if not user32.IsWindowVisible(hwnd):
        flags |= SWP_SHOWWINDOW
    ok = user32.SetWindowPos(hwnd, HWND_NOTOPMOST, x, y, w, h, flags)
    if not ok:
        err = ctypes.get_last_error()
        return False, ("失败，错误码 %d%s" % (err, "（拒绝访问，需管理员）" if err == 5 else ""))
    if minimize_after:
        user32.ShowWindow(hwnd, SW_MINIMIZE)
    return True, "已转为窗口 %dx%d" % (w, h)


def to_fullscreen_mode(win):
    hwnd = win["hwnd"]
    if not user32.IsWindow(hwnd):
        return False, "窗口已关闭"
    style = _GetWindowLong(hwnd, GWL_STYLE)
    ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
    new_style = (style & ~(WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX |
                           WS_THICKFRAME | WS_MAXIMIZEBOX)) | WS_POPUP
    new_ex = ex | WS_EX_TOPMOST
    _SetWindowLong(hwnd, GWL_STYLE, new_style)
    _SetWindowLong(hwnd, GWL_EXSTYLE, new_ex)

    vx, vy, vw, vh = screen_metrics()
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    flags = SWP_FRAMECHANGED | SWP_NOACTIVATE
    if not user32.IsWindowVisible(hwnd):
        flags |= SWP_SHOWWINDOW
    ok = user32.SetWindowPos(hwnd, HWND_TOPMOST, vx, vy, vw, vh, flags)
    return (bool(ok), "已还原全屏置顶" if ok else "还原失败")


def needs_window_mode(win):
    style = _GetWindowLong(win["hwnd"], GWL_STYLE)
    ex = _GetWindowLong(win["hwnd"], GWL_EXSTYLE)
    return (not (style & WS_CAPTION)) or bool(ex & WS_EX_TOPMOST)


def dark_titlebar(root):
    """Win10 20H1+/Win11：让系统标题栏变暗，配合深色界面。"""
    try:
        hwnd = user32.GetParent(root.winfo_id())
        v = ctypes.c_int(1)
        for attr in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        pass


# ----------------------------------------------------------------- 自绘按钮
class CvButton(object):
    def __init__(self, ui, key, text, x, y, w, h, style, cmd, font):
        self.cv = ui.cv
        self.key = key
        self.text = text
        self.style = style          # primary / ghost / danger
        self.cmd = cmd
        self.state = "normal"
        self.enabled = True
        self.tag = "btn_" + key

        self.id_glow = None
        if style == "primary":
            self.id_glow = rrect(self.cv, x - 3, y - 3, x + w + 3, y + h + 3, 13,
                                 fill="", outline="#3A0E16", width=1,
                                 tags=("ui", self.tag))
        self.id_bg = rrect(self.cv, x, y, x + w, y + h, 10,
                           fill=self._fill(), outline=self._outline(),
                           width=1, tags=("ui", self.tag))
        self.id_tx = self.cv.create_text(
            x + w / 2.0, y + h / 2.0, text=text, fill=self._fg(),
            font=font, tags=("ui", self.tag))

        for ev, fn in (("<Enter>", self.on_enter), ("<Leave>", self.on_leave),
                       ("<Button-1>", self.on_press),
                       ("<ButtonRelease-1>", self.on_release)):
            self.cv.tag_bind(self.tag, ev, fn)

    def _fill(self):
        if not self.enabled:
            return "#1A1A22" if self.style != "primary" else "#3A151C"
        if self.style == "primary":
            return {"normal": C_ACCENT, "hover": C_ACCENT2, "press": "#B80E22"}[self.state]
        if self.style == "danger":
            return {"normal": "#3A1620", "hover": "#4E1C29", "press": "#2C1018"}[self.state]
        return {"normal": "#1A1A23", "hover": "#242432", "press": "#141420"}[self.state]

    def _outline(self):
        if self.style == "primary":
            return {"normal": "#FF5C74", "hover": "#FF8598", "press": "#8E0A1B"}[self.state]
        if self.style == "danger":
            return C_ACCENT
        return {"normal": C_LINE, "hover": C_ACCENT, "press": C_ACCENT2}[self.state]

    def _fg(self):
        if not self.enabled:
            return "#4A4A58"
        if self.style == "primary":
            return "#FFFFFF"
        if self.style == "danger":
            return "#FF8A9C"
        return "#DCDCE6" if self.state == "hover" else "#C9C9D6"

    def _apply(self):
        if self.id_glow is not None:
            self.cv.itemconfigure(
                self.id_glow,
                outline=("#5A1220" if self.state != "normal" and self.enabled
                         else "#3A0E16"))
        self.cv.itemconfigure(self.id_bg, fill=self._fill(),
                              outline=self._outline(),
                              width=2 if self.state == "hover" else 1)
        self.cv.itemconfigure(self.id_tx, fill=self._fg())

    def on_enter(self, e):
        if not self.enabled:
            return
        self.state = "hover"
        self._apply()
        self.cv.configure(cursor="hand2")

    def on_leave(self, e):
        self.state = "normal"
        self._apply()
        self.cv.configure(cursor="")

    def on_press(self, e):
        if not self.enabled:
            return
        self.state = "press"
        self._apply()

    def on_release(self, e):
        if not self.enabled:
            return
        self.state = "hover"
        self._apply()
        if self.cmd:
            self.cmd()

    def set_text(self, text, style=None):
        self.text = text
        if style:
            self.style = style
        self.cv.itemconfigure(self.id_tx, text=text)
        self._apply()


# ----------------------------------------------------------------- 主界面
class Ui(object):
    def __init__(self, root):
        self.root = root
        self.watching = False
        self.current = None
        self.count = 0
        self.giveup = False      # 被极域反复拉回后：彻底停止自动尝试
        self.scale = 0.85
        self.phase = 0.0
        self.w, self.h = 760, 560
        self._bg_img = None
        self._bg_src = None
        self._bg_item = None
        self._last_size = (0, 0)
        self._resize_job = None
        self.seg_items = {}
        self.buttons = {}

        root.title("%s  v%s" % (APP_NAME, APP_VER))
        root.geometry("760x560")
        root.minsize(700, 520)
        root.configure(bg=C_BG)

        ico = res_path("assets", "icon.ico")
        try:
            root.iconbitmap(ico)
        except Exception:
            pass

        self.cv = tk.Canvas(root, bg=C_BG, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)

        self.f_title = ("Microsoft YaHei UI", 17, "bold")
        self.f_sub = ("Segoe UI", 9)
        self.f_body = ("Microsoft YaHei UI", 10)
        self.f_small = ("Microsoft YaHei UI", 9)
        self.f_btn = ("Microsoft YaHei UI", 10, "bold")
        self.f_mono = ("Consolas", 9)

        self._load_bg_source()
        self._make_avatar(ico)

        self.log = tk.Text(self.cv, bd=0, highlightthickness=0, bg=C_PANEL2,
                           fg="#C9C9D6", insertbackground=C_TEXT,
                           font=self.f_mono, wrap="word", padx=14, pady=10,
                           spacing1=1, spacing3=3, selectbackground="#3A1620")
        self.log.place(x=0, y=0, width=10, height=10)
        self.log.tag_configure("t", foreground="#5A5A6A")
        self.log.tag_configure("ok", foreground=C_OK)
        self.log.tag_configure("err", foreground=C_ACCENT2)
        self.log.tag_configure("hl", foreground="#FFFFFF")
        self.log.configure(state="disabled")

        self.root.report_callback_exception = self._on_callback_error
        self.cv.bind("<Configure>", self._on_configure)
        self._build()
        self._log("就绪。%s" % ("已获得管理员权限" if is_admin()
                              else "当前非管理员，可能无法修改极域窗口"), "t")
        self._fade_in()
        self._tick()
        self._animate()

    # ---------------------------------------------------------- 资源
    def _load_bg_source(self):
        p = res_path("assets", "bg.jpg")
        if Image and os.path.exists(p):
            try:
                self._bg_src = Image.open(p).convert("RGB")
            except Exception:
                self._bg_src = None

    def _make_avatar(self, ico_path):
        self.avatar = None
        if not Image or not os.path.exists(ico_path):
            return
        try:
            im = Image.open(ico_path).convert("RGBA").resize((46, 46), Image.LANCZOS)
            mask = Image.new("L", (46, 46), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, 45, 45], 13, fill=255)
            im.putalpha(mask)
            self.avatar = ImageTk.PhotoImage(im)
        except Exception:
            self.avatar = None

    def _compose_bg(self, w, h):
        if not self._bg_src:
            return None
        src = self._bg_src
        s = max(w / float(src.width), h / float(src.height))
        nw, nh = int(src.width * s) + 1, int(src.height * s) + 1
        im = src.resize((nw, nh), Image.LANCZOS)
        left = (nw - w) // 2
        top = (nh - h) // 2
        im = im.crop((left, top, left + w, top + h))
        im = Image.blend(im, Image.new("RGB", (w, h), (8, 8, 12)), 0.24)
        grad = Image.new("L", (1, h))
        for y in range(h):
            grad.putpixel((0, y), int(70 + 120 * (y / float(h))))
        im = Image.composite(Image.new("RGB", (w, h), (6, 6, 9)), im,
                             grad.resize((w, h)))
        return ImageTk.PhotoImage(im)

    def _draw_bg(self):
        w, h = self.w, self.h
        if self._bg_src:
            self._bg_img = self._compose_bg(w, h)
            if self._bg_item is None:
                self._bg_item = self.cv.create_image(0, 0, image=self._bg_img,
                                                     anchor="nw")
            else:
                self.cv.itemconfigure(self._bg_item, image=self._bg_img)
            self.cv.tag_lower(self._bg_item)

    # ---------------------------------------------------------- 布局
    def _on_configure(self, e):
        if (e.width, e.height) == self._last_size:
            return
        self._last_size = (e.width, e.height)
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(60, self._build)

    def _build(self):
        self.w = max(self.cv.winfo_width(), 700)
        self.h = max(self.cv.winfo_height(), 500)
        self.cv.delete("ui")
        self.buttons = {}
        self._draw_bg()

        w, h, M = self.w, self.h, 20

        # 顶部
        if self.avatar:
            self.cv.create_image(M, M + 23, image=self.avatar, anchor="w",
                                 tags="ui")
            tx = M + 58
        else:
            tx = M
        self.cv.create_text(tx, M + 12, text=APP_NAME, anchor="w",
                            font=self.f_title, fill=C_TEXT, tags="ui")
        self.cv.create_text(tx, M + 34,
                            text="MYTHWARE V6  ·  SCREEN BROADCAST  →  WINDOW",
                            anchor="w", font=self.f_sub, fill="#6E6E80", tags="ui")

        pill_w, pill_h = 118, 34
        px = w - M - pill_w
        rrect(self.cv, px, M + 6, px + pill_w, M + 6 + pill_h, 17,
              fill="#16161F", outline=C_LINE, width=1, tags="ui")
        self._pd1 = self.cv.create_oval(px + 14, M + 19, px + 22, M + 27,
                                        fill=C_SUB, outline="", tags="ui")
        self._ptx = self.cv.create_text(px + 30, M + 6 + pill_h / 2.0,
                                        text="待机", anchor="w",
                                        font=self.f_small, fill=C_SUB, tags="ui")

        # 状态卡
        py1, py2 = 92, 200
        rrect(self.cv, M, py1, w - M, py2, 14, fill=C_PANEL,
              outline=C_LINE, width=1, tags="ui")
        rrect(self.cv, M, py1 + 18, M + 3, py2 - 18, 2, fill=C_ACCENT,
              outline="", tags="ui")

        self._state_tx = self.cv.create_text(
            M + 22, py1 + 32, text="等待广播", anchor="w",
            font=("Microsoft YaHei UI", 16, "bold"), fill=C_TEXT, tags="ui")
        self._detail_tx = self.cv.create_text(
            M + 22, py1 + 60, text="点击「开始监控」，教师投屏时会自动转为窗口",
            anchor="w", font=self.f_body, fill=C_SUB, tags="ui")
        self._meta_tx = self.cv.create_text(
            M + 22, py1 + 84, text="HWND  —", anchor="w",
            font=self.f_mono, fill="#5E5E70", tags="ui")

        self._cx, self._cy = w - M - 78, py1 + 54
        self._ring2 = self.cv.create_oval(self._cx - 26, self._cy - 26,
                                          self._cx + 26, self._cy + 26,
                                          outline="#20202A", width=1, tags="ui")
        self._ring1 = self.cv.create_oval(self._cx - 18, self._cy - 18,
                                          self._cx + 18, self._cy + 18,
                                          outline="#20202A", width=1, tags="ui")
        self._dot = self.cv.create_oval(self._cx - 5, self._cy - 5,
                                        self._cx + 5, self._cy + 5,
                                        fill=C_SUB, outline="", tags="ui")
        self._scan = self.cv.create_line(M + 6, py1 + 6, w - M - 6, py1 + 6,
                                         fill="#1A1A24", width=1,
                                         state="hidden", tags="ui")

        # 按钮
        by, bh, gap, prim_w = py2 + 16, 44, 10, 132
        rest = (w - 2 * M - prim_w - 3 * gap) / 3.0
        specs = [("start", "开始监控" if not self.watching else "停止监控",
                  prim_w, "primary" if not self.watching else "danger",
                  self.on_toggle),
                 ("apply", "立即窗口化", rest, "ghost", self.on_apply),
                 ("min", "最小化", rest, "ghost", self.on_min),
                 ("restore", "还原全屏", rest, "ghost", self.on_restore)]
        x = M
        for key, label, bw, style, cb in specs:
            self.buttons[key] = CvButton(self, key, label, x, by, bw, bh,
                                         style, cb, self.f_btn)
            x += bw + gap

        # 比例分段
        sy = by + bh + 22
        self.cv.create_text(M, sy + 14, text="窗口占比", anchor="w",
                            font=self.f_small, fill=C_SUB, tags="ui")
        self.seg_items = {}
        sx = M + 74
        for val in (1.0, 0.9, 0.85, 0.7, 0.5):
            sw, sh = 58, 28
            tag = "seg_%d" % int(val * 100)
            sel = abs(val - self.scale) < 0.001
            bg_id = rrect(self.cv, sx, sy, sx + sw, sy + sh, 7,
                          fill=(C_ACCENT if sel else "#1A1A23"),
                          outline=(C_ACCENT if sel else C_LINE), width=1,
                          tags=("ui", tag))
            tx_id = self.cv.create_text(sx + sw / 2, sy + sh / 2,
                                        text="%d%%" % int(val * 100),
                                        font=self.f_small,
                                        fill=("#FFFFFF" if sel else "#9A9AAA"),
                                        tags=("ui", tag))
            self.seg_items[val] = (bg_id, tx_id)
            self.cv.tag_bind(tag, "<Enter>",
                             lambda e, v=val: self._seg_hover(v, True))
            self.cv.tag_bind(tag, "<Leave>",
                             lambda e, v=val: self._seg_hover(v, False))
            self.cv.tag_bind(tag, "<Button-1>", lambda e, v=val: self.set_scale(v))
            sx += sw + 6

        # 日志面板
        ly1 = sy + sh + 18
        ly2 = h - 18
        rrect(self.cv, M, ly1, w - M, ly2, 14, fill=C_PANEL,
              outline=C_LINE, width=1, tags="ui")
        self.cv.create_text(M + 16, ly1 + 20, text="运行日志", anchor="w",
                            font=("Microsoft YaHei UI", 9, "bold"),
                            fill="#7A7A8C", tags="ui")
        self.cv.create_text(w - M - 16, ly1 + 20, text="滚轮翻看",
                            anchor="e", font=self.f_small,
                            fill="#4C4C5C", tags="ui")
        self.log.place(x=M + 8, y=ly1 + 32, width=w - 2 * M - 16,
                       height=max(60, ly2 - ly1 - 42))

        self._refresh_state()

    # ---------------------------------------------------------- 交互
    def _seg_hover(self, val, on):
        if abs(val - self.scale) < 0.001:
            return
        bg_id = self.seg_items[val][0]
        self.cv.itemconfigure(bg_id, outline=(C_ACCENT2 if on else C_LINE))
        self.cv.configure(cursor="hand2" if on else "")

    def set_scale(self, val):
        self.scale = val
        for v, (bg_id, tx_id) in self.seg_items.items():
            sel = abs(v - val) < 0.001
            self.cv.itemconfigure(bg_id,
                                  fill=(C_ACCENT if sel else "#1A1A23"),
                                  outline=(C_ACCENT if sel else C_LINE))
            self.cv.itemconfigure(tx_id,
                                  fill=("#FFFFFF" if sel else "#9A9AAA"))
        self._log("窗口占比设为 %d%%" % int(val * 100), "t")

    def on_toggle(self):
        self.watching = not self.watching
        self.giveup = False
        self.apply_hist = []
        b = self.buttons["start"]
        if self.watching:
            b.set_text("停止监控", "danger")
            self._log("开始监控，教师投屏时会自动接管", "hl")
        else:
            b.set_text("开始监控", "primary")
            self._log("已停止监控", "t")
        self._refresh_state()

    def on_apply(self):
        self.giveup = False
        self.last_apply = 0
        self.apply_hist = []
        w = self.current or (find_windows(TARGET_PROCESSES, 0.35) or [None])[0]
        if not w:
            self._log("未找到广播窗口，先让教师开一次屏幕广播", "err")
            self._toast("未找到广播窗口", C_WARN)
            return
        ok, info = to_window_mode(w, self.scale)
        self._log(info, "ok" if ok else "err")
        if ok:
            self.count += 1
            self._toast("已转为窗口 · %d%%" % int(self.scale * 100), C_ACCENT)
        self._refresh_state()

    def on_min(self):
        w = self.current
        if not w:
            self._log("未找到广播窗口", "err")
            return
        user32.ShowWindow(w["hwnd"], SW_MINIMIZE)
        self._log("广播窗口已最小化", "ok")
        self._toast("已最小化到任务栏", C_ACCENT)

    def on_restore(self):
        w = self.current or (find_windows(TARGET_PROCESSES, 0.35) or [None])[0]
        if not w:
            self._log("未找到广播窗口", "err")
            return
        ok, info = to_fullscreen_mode(w)
        self._log(info, "ok" if ok else "err")
        if ok:
            self._toast("已还原全屏置顶", C_WARN)
        self._refresh_state()

    # ---------------------------------------------------------- 状态
    def _refresh_state(self):
        if not hasattr(self, "_state_tx"):
            return
        if self.current:
            done = not needs_window_mode(self.current)
            color = C_ACCENT
            label = "已接管" if done else ("无法接管" if self.giveup else "已发现")
            state = ("已接管广播窗口" if done else
                     ("极域锁死了全屏" if self.giveup else "检测到广播窗口"))
            detail = ("已转为可最小化窗口，可拖动标题栏" if done else
                      ("它每次都会拉回全屏，已不再自动重试；可点「立即窗口化」再试一次"
                       if self.giveup else "点「立即窗口化」手动接管"))
            r = self.current["rect"]
            meta = "HWND 0x%X   ·   %s   ·   %d×%d" % (
                self.current["hwnd"], self.current["cls"][:18], r[2], r[3])
        elif self.watching:
            color, label = C_ACCENT, "监控中"
            state, detail = "等待教师投屏", "正在监听 StudentMain.exe 的顶层窗口…"
            meta = "已接管 %d 次    ·    轮询间隔 500ms" % self.count
        else:
            color, label = C_SUB, "待机"
            state, detail = "等待广播", "点击「开始监控」，教师投屏时会自动转为窗口"
            meta = "已接管 %d 次" % self.count

        self.cv.itemconfigure(self._ptx, text=label, fill=color)
        self.cv.itemconfigure(self._pd1, fill=color)
        self.cv.itemconfigure(self._dot, fill=color)
        self.cv.itemconfigure(self._state_tx, text=state)
        self.cv.itemconfigure(self._detail_tx, text=detail)
        self.cv.itemconfigure(self._meta_tx, text=meta)

    def _on_callback_error(self, exc, val, tb):
        try:
            self._log("内部错误：%s" % val, "err")
        except Exception:
            pass

    def _log(self, msg, tag=None):
        now = time.time()
        if msg == getattr(self, "_last_msg", None) and \
                now - getattr(self, "_last_msg_t", 0) < 3.0:
            return
        self._last_msg, self._last_msg_t = msg, now
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S  "), "t")
        self.log.insert("end", msg + "\n", tag or "")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---------------------------------------------------------- 动效
    def _fade_in(self):
        try:
            self.root.attributes("-alpha", 0.0)
        except Exception:
            return

        def step(a=0.0):
            a += 0.14
            try:
                self.root.attributes("-alpha", min(1.0, a))
            except Exception:
                return
            if a < 1.0:
                self.root.after(16, step, a)

        self.root.after(30, step)

    def _toast(self, text, color):
        self.cv.delete("toast")
        w = 210
        x1 = self.w - M_TOAST_MARGIN - w
        y1 = self.h - 64
        rrect(self.cv, x1, y1, x1 + w, y1 + 44, 12, fill="#1A0A10",
              outline=color, width=1, tags=("toast",))
        self.cv.create_text(x1 + 18, y1 + 22, text="●", fill=color,
                            font=("Segoe UI", 9), tags=("toast",))
        self.cv.create_text(x1 + 36, y1 + 22, text=text, anchor="w",
                            font=self.f_body, fill="#FFFFFF", tags=("toast",))

        def rise(step=0):
            if step > 10 or not self.cv.find_withtag("toast"):
                return
            self.cv.move("toast", 0, -1.0)
            self.root.after(16, rise, step + 1)

        rise()
        self.root.after(2600, lambda: self.cv.delete("toast"))

    def _animate(self):
        """脉冲环 + 扫描线，45ms 一帧。"""
        self.phase = (self.phase + 0.045) % 1.0
        try:
            if self.watching:
                for i, ring in enumerate((self._ring1, self._ring2)):
                    t = (self.phase + i * 0.5) % 1.0
                    r = 8 + 22 * t
                    self.cv.coords(ring, self._cx - r, self._cy - r,
                                   self._cx + r, self._cy + r)
                    self.cv.itemconfigure(ring, outline=lerp(C_ACCENT, C_PANEL, t))
                self.cv.itemconfigure(self._scan, state="normal")
                y = 98 + 96 * ((self.phase * 2.2) % 1.0)
                self.cv.coords(self._scan, 26, y, self.w - 26, y)
                self.cv.itemconfigure(self._scan,
                                      fill=lerp(C_PANEL, "#5A1220", 0.75))
            else:
                self.cv.itemconfigure(self._scan, state="hidden")
                for ring, r in ((self._ring1, 18), (self._ring2, 26)):
                    self.cv.itemconfigure(ring, outline="#20202A")
                    self.cv.coords(ring, self._cx - r, self._cy - r,
                                   self._cx + r, self._cy + r)
        except Exception:
            pass
        self.root.after(45, self._animate)

    # ---------------------------------------------------------- 主循环
    def _tick(self):
        try:
            wins = find_windows(TARGET_PROCESSES, 0.85)
            if not wins and self.current:
                p = probe(self.current["hwnd"])
                if p and p["proc"] in TARGET_PROCESSES:
                    wins = [p]
            before = self.current
            self.current = wins[0] if wins else None
            if self.current and not before:
                self.giveup = False
                self.apply_hist = []
                self._log("发现广播窗口 0x%X（%s）"
                          % (self.current["hwnd"], self.current["cls"]), "hl")
            if not self.current and before:
                self._log("广播窗口已关闭", "t")
            now = time.time()
            too_soon = now - getattr(self, "last_apply", 0) < 1.5
            if (self.watching and self.current
                    and needs_window_mode(self.current)
                    and not self.giveup and not too_soon):
                ok, info = to_window_mode(self.current, self.scale)
                self.last_apply = now
                if ok:
                    self.count += 1
                    hist = [t for t in getattr(self, "apply_hist", [])
                            if now - t < 10.0]
                    hist.append(now)
                    self.apply_hist = hist
                    if len(hist) >= 3:
                        self.giveup = True
                        self.apply_hist = []
                        self._log("极域每次都会把窗口拉回全屏，已彻底停止自动尝试"
                                  "（不再反复闪屏）；要再试请手动点「立即窗口化」", "err")
                        self._toast("已停止自动尝试", C_WARN)
                    else:
                        self._log(info, "ok")
                        self._toast("已自动窗口化 · %d%%" % int(self.scale * 100),
                                    C_ACCENT)
                else:
                    self._log(info, "err")
            self._refresh_state()
        except Exception as e:
            self._log("异常：%s" % e, "err")
        finally:
            self.root.after(500, self._tick)


M_TOAST_MARGIN = 30


def main():
    if "--only" in sys.argv:        # 只监控 --process 指定的进程（调试用）
        TARGET_PROCESSES.clear()
    for i, a in enumerate(sys.argv):
        if a == "--process" and i + 1 < len(sys.argv):
            TARGET_PROCESSES.add(sys.argv[i + 1].lower())
    if "--no-elevate" not in sys.argv and not is_admin():
        if relaunch_elevated([a for a in sys.argv[1:]]):
            return 0

    root = tk.Tk()
    ui = Ui(root)
    root.after(150, lambda: dark_titlebar(root))
    if "--watch" in sys.argv:
        ui.watching = True
        ui.buttons["start"].set_text("停止监控", "danger")
        ui._log("已按命令行参数自动开始监控", "hl")
        ui._refresh_state()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
