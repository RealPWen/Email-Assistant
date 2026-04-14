#!/bin/bash

# DeepMail AI 启动脚本 (Shell 包装器)
# 现在统一使用 Python 版本的 run_service.py 来实现全平台兼容性

if ! command -v python3 &> /dev/null
then
    echo "❌ 错误: 未发现 python3 命令，请先安装 Python 3。"
    exit 1
fi

python3 run_service.py
