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

# 安装依赖
echo "[1/2] 安装依赖..."
pip3 install -r requirements.txt -q

# 启动服务
echo "[2/2] 启动服务..."
echo ""
echo "  访问地址: http://127.0.0.1:5000"
echo "  按 Ctrl+C 停止服务"
echo "===================================="
echo ""

python3 app.py
