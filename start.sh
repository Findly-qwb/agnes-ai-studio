#!/bin/bash
echo "===================================="
echo "  Agnes AI Studio - 启动中..."
echo "===================================="
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 Python3，请先安装 Python 3.8+"
    exit 1
fi

# 在项目目录创建并使用隔离的虚拟环境，避免修改 Homebrew 管理的 Python。
PROJECT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$PROJECT_DIR" || exit 1
VENV_DIR="$PROJECT_DIR/venv"
if [ ! -x "$VENV_DIR/bin/python" ] || ! "$VENV_DIR/bin/python" -m pip check > /dev/null 2>&1; then
    echo "[准备] 创建或修复虚拟环境..."
    python3 -m venv --clear "$VENV_DIR" || exit 1
fi

# 安装依赖
echo "[1/2] 安装依赖..."
"$VENV_DIR/bin/python" -m pip install -r requirements.txt -q || exit 1

# 启动服务
echo "[2/2] 启动服务..."
echo ""
echo "  启动后将输出实际访问地址"
echo "  按 Ctrl+C 停止服务"
echo "===================================="
echo ""

"$VENV_DIR/bin/python" app.py
