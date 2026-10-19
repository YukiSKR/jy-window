@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   重新打包 JyWindow.exe
echo   需要 Python 3.8+（且带 tkinter）
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [x] 没找到 python，请先安装 Python 并勾选 Add to PATH
    pause
    exit /b 1
)

echo [1/2] 安装 / 更新 PyInstaller ...
python -m pip install --upgrade --quiet pyinstaller
if errorlevel 1 (
    echo [x] PyInstaller 安装失败，检查网络或换国内镜像：
    echo     python -m pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
    pause
    exit /b 1
)

echo [2/2] 打包 ...
python -m PyInstaller --noconfirm --onefile --noconsole --name JyWindow ^
    --distpath . --workpath build --specpath . src\jywin_gui.py
if errorlevel 1 (
    echo [x] 打包失败
    pause
    exit /b 1
)

rmdir /s /q build 2>nul
del /q JyWindow.spec 2>nul
del /s /q src\__pycache__ 2>nul

echo.
echo [√] 完成：%~dp0JyWindow.exe
pause
