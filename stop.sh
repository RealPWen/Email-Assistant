#!/bin/bash

# DeepMail AI 停止脚本
# 作者: Antigravity AI

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${RED}=======================================${NC}"
echo -e "${RED}    🛑 正在停止 DeepMail AI 服务...    ${NC}"
echo -e "${RED}=======================================${NC}"

# 停止后端
if [ -f ".api.pid" ]; then
    API_PID=$(cat .api.pid)
    echo -e "${YELLOW}正在中止 API 服务 (PID: $API_PID)...${NC}"
    kill $API_PID 2>/dev/null
    rm .api.pid
    echo -e "${GREEN}✅ API 服务已停止。${NC}"
else
    echo -e "${YELLOW}ℹ️ 未发现运行中的 API 服务 PID。${NC}"
fi

# 停止调度器
if [ -f ".scheduler.pid" ]; then
    SCHED_PID=$(cat .scheduler.pid)
    echo -e "${YELLOW}正在中止 调度器服务 (PID: $SCHED_PID)...${NC}"
    kill $SCHED_PID 2>/dev/null
    rm .scheduler.pid
    echo -e "${GREEN}✅ 调度器服务已停止。${NC}"
else
    echo -e "${YELLOW}ℹ️ 未发现运行中的 调度器服务 PID。${NC}"
fi

# 备选：清理可能残余的相关进程
echo -e "${YELLOW}正在清理残余进程...${NC}"
pkill -f "api_main.py"
pkill -f "scheduler.py"

echo -e "${RED}---------------------------------------${NC}"
echo -e "${GREEN}✨ 所有服务已停止。${NC}"
echo -e "${RED}=======================================${NC}"
