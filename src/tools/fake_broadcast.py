# -*- coding: utf-8 -*-
"""
自测用的「假广播窗口」。

它创建一个和极域屏幕广播窗口同样属性的窗口：
全屏 1600x900、置顶(WS_EX_TOPMOST)、无边框(WS_POPUP)、类名 TESTBCASTWND。
没有老师开广播时，可以用它验证本工具是否生效。

用法：
    python fake_broadcast.py            # 起一个假广播窗口
    (然后运行 JyWindow.exe --process python.exe --no-elevate)
    Ctrl+C 关闭
"""

import ctypes
import sys
from ctypes import wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32")

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


def _wndproc(hwnd, msg, wparam, lparam):
    if msg == 0x0002:  # WM_DESTROY
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


wndproc = WNDPROC(_wndproc)


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.RegisterClassW.restype = wt.ATOM
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASS)]
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wt.HWND, wt.HMENU,
                                   wt.HINSTANCE, wt.LPVOID]

wc = WNDCLASS()
wc.lpfnWndProc = wndproc
wc.lpszClassName = "TESTBCASTWND"
wc.hInstance = kernel32.GetModuleHandleW(None)
user32.RegisterClassW(ctypes.byref(wc))

sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
hwnd = user32.CreateWindowExW(0x00000008, "TESTBCASTWND", "屏幕广播窗口",
                              0x80000000, 0, 0, sw, sh,
                              None, None, wc.hInstance, None)
if not hwnd:
    print("创建窗口失败，错误码", ctypes.get_last_error())
    sys.exit(1)
user32.ShowWindow(hwnd, 5)
print("假广播窗口已创建 hwnd=0x%X  %dx%d，Ctrl+C 退出" % (hwnd, sw, sh), flush=True)

msg = wt.MSG()
while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
    user32.TranslateMessage(ctypes.byref(msg))
    user32.DispatchMessageW(ctypes.byref(msg))
