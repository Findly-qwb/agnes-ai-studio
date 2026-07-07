@echo off
chcp 65001 >nul
echo =============================================
echo   Agnes AI Studio - PyInstaller 打包工具
echo =============================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo   下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] 安装 PyInstaller...
pip install pyinstaller -q

echo [2/3] 安装项目依赖...
pip install flask flask-cors requests -q

echo [3/3] 开始打包...
echo.
echo   这可能需要几分钟，请耐心等待...
echo.

pyinstaller --clean --noconfirm Agnes-AI-Studio.spec

if errorlevel 1 (
    echo.
    echo [失败] 打包出错，请检查上方错误信息
    pause
    exit /b 1
)

echo.
echo =============================================
echo   打包完成！
echo.
echo   输出文件: dist\Agnes-AI-Studio.exe
echo.
echo   使用方法:
echo     1. 将 dist\Agnes-AI-Studio.exe 复制到任意目录
echo     2. 双击运行
echo     3. 浏览器会自动打开 http://127.0.0.1:5000
echo =============================================
echo.
echo 按任意键打开输出目录...
pause >nul
start explorer dist
