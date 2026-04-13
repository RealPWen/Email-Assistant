#!/bin/bash

# DeepMail AI 启动脚本
# 作者: Antigravity AI

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}    🚀 DeepMail AI 启动程序启动中...    ${NC}"
echo -e "${BLUE}=======================================${NC}"

# 1. 环境检查与引导
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  未发现 .env 配置文件，正在引导您进行系统配置...${NC}"
    echo -e "${YELLOW}---------------------------------------${NC}"
    
    # 引导输入邮箱地址
    read -p "📧 请输入您的邮箱地址 (例如: user@163.com): " EMAIL_USER
    while [ -z "$EMAIL_USER" ]; do
        echo -e "${RED}❗ 邮箱地址不能为空，请重新输入。${NC}"
        read -p "📧 请输入您的邮箱地址: " EMAIL_USER
    done

    # 引导输入邮箱授权码
    # 使用 -s 参数隐藏输入更安全
    echo -n -e "🔑 请输入邮箱授权码/应用密码 (输入时不可见): "
    read -s EMAIL_AUTH_CODE
    echo ""
    while [ -z "$EMAIL_AUTH_CODE" ]; do
        echo -e "${RED}❗ 授权码不能为空，请重新输入。${NC}"
        echo -n -e "🔑 请输入邮箱授权码/应用密码: "
        read -s EMAIL_AUTH_CODE
        echo ""
    done

    # 引导输入 DeepSeek API Key
    echo -n -e "🤖 请输入 DeepSeek API Key (sk-...): "
    read -s DEEPSEEK_API_KEY
    echo ""
    while [ -z "$DEEPSEEK_API_KEY" ]; do
        echo -e "${RED}❗ API Key 不能为空，请重新输入。${NC}"
        echo -n -e "🤖 请输入 DeepSeek API Key: "
        read -s DEEPSEEK_API_KEY
        echo ""
    done

    # 生成 .env 文件
    cat <<EOF > .env
# --- 邮箱配置 ---
EMAIL_USER=$EMAIL_USER
EMAIL_AUTH_CODE=$EMAIL_AUTH_CODE

# --- DeepSeek 官方 API 配置 ---
DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
EOF

    echo -e "${GREEN}✅ .env 配置文件已成功生成！${NC}"
    echo -e "${YELLOW}---------------------------------------${NC}"
fi

# 2. 系统核心功能自检
echo -e "${YELLOW}🔍 正在进行系统核心功能自检...${NC}"
python3 verify_system.py
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 系统自检未通过！请根据上方错误提示修正您的 .env 配置。${NC}"
    echo -e "${YELLOW}💡 提示: 如果输入有误，您可以删除 .env 文件后再次运行此脚本重新配置。${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 系统自检通过，准备启动服务...${NC}"

# 3. 初始同步与数据库检查
if [ ! -f "data/emails.db" ]; then
    echo -e "${YELLOW}📦 正在初始化数据库并进行首次同步 (请稍候)...${NC}"
    python3 tools/fetch_emails.py --max-scan 50
else
    echo -e "${YELLOW}🔄 正在同步最新邮件...${NC}"
    # 每次启动时仅快速扫描最近 20 封邮件以确保即时更新
    python3 tools/fetch_emails.py --max-scan 20
fi

# 4. 创建日志目录
mkdir -p logs

# 4. 启动后端仪表盘 (FastAPI)
echo -e "${YELLOW}📂 正在启动 Dashboard 后端...${NC}"
nohup python3 -u api_main.py > logs/api.log 2>&1 &
API_PID=$!
echo $API_PID > .api.pid
echo -e "${GREEN}✅ 后端已启动 (PID: $API_PID)，日志: logs/api.log${NC}"

# 5. 启动自动同步调度器 (Scheduler)
echo -e "${YELLOW}⏰ 正在启动 自动同步调度器...${NC}"
nohup python3 -u tools/scheduler.py --interval 10 > logs/scheduler.log 2>&1 &
SCHEDULER_PID=$!
echo $SCHEDULER_PID > .scheduler.pid
echo -e "${GREEN}✅ 调度器已启动 (PID: $SCHEDULER_PID)，日志: logs/scheduler.log${NC}"

# 6. 自动打开网页 (MacOS)
echo -e "${YELLOW}🌐 正在为您打开 Dashboard 界面...${NC}"
sleep 2
open "http://localhost:8000"

echo -e "${BLUE}---------------------------------------${NC}"
echo -e "${GREEN}✨ 全部服务已在后台启动！${NC}"
echo -e "${BLUE}🔗 访问地址: ${NC}${YELLOW}http://localhost:8000${NC}"
echo -e "${BLUE}📝 停止服务请运行: ${NC}${YELLOW}./stop.sh${NC}"
echo -e "${BLUE}=======================================${NC}"
