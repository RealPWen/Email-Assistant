import os
import sys
import subprocess
import time
import webbrowser
import getpass
from pathlib import Path

# --- Constants ---
BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"
ENV_FILE = BASE_DIR / ".env"
API_PID_FILE = BASE_DIR / ".api.pid"
SCHEDULER_PID_FILE = BASE_DIR / ".scheduler.pid"

def print_header(text, color="blue"):
    colors = {
        "green": "\033[0;32m",
        "blue": "\033[0;34m",
        "yellow": "\033[1;33m",
        "red": "\033[0;31m",
        "nc": "\033[0m"
    }
    # Windows command prompt doesn't always support ANSI, but it's okay for modern terminals
    c = colors.get(color, colors["nc"])
    nc = colors["nc"]
    print(f"{c}======================================={nc}")
    print(f"{c}    {text}    {nc}")
    print(f"{c}======================================={nc}")

def setup_env():
    if ENV_FILE.exists():
        return

    print_header("⚠️  未发现 .env 配置文件，正在引导您进行系统配置...", "yellow")
    print("-" * 40)
    
    print("\n💡 【前置准备：HKU (Outlook) 邮件转发配置】")
    print("如果您是香港大学的学生或教职工，请先登录 Outlook 开启邮件转发到您的 163 邮箱。")
    print("文档参考: https://outlook.office365.com/mail/options/mail/forwarding\n")

    email_user = input("📧 请输入您的邮箱地址 (例如: user@163.com): ").strip()
    while not email_user:
        email_user = input("❗ 邮箱不能为空，请重新输入: ").strip()

    print("\n💡 【如何获取 163 邮箱授权码？】")
    print("1. 登录 mail.163.com -> 设置 -> POP3/SMTP/IMAP")
    print("2. 开启 IMAP/SMTP 服务并获取生成的授权码。\n")
    
    email_auth = getpass.getpass("🔑 请输入邮箱授权码 (输入时不可见): ").strip()
    while not email_auth:
        email_auth = getpass.getpass("❗ 授权码不能为空，请重新输入: ").strip()

    deepseek_key = getpass.getpass("🤖 请输入 DeepSeek API Key (sk-...): ").strip()
    while not deepseek_key:
        deepseek_key = getpass.getpass("❗ API Key 不能为空，请重新输入: ").strip()

    env_content = f"""# --- 邮箱配置 ---
EMAIL_USER={email_user}
EMAIL_AUTH_CODE={email_auth}

# --- DeepSeek 官方 API 配置 ---
DEEPSEEK_API_KEY={deepseek_key}
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
"""
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(env_content)
    
    print("\n✅ .env 配置文件已成功生成！")
    print("-" * 40)

def run_self_check():
    print(f"\n🔍 正在进行系统核心功能自检...")
    # Use the same python executable to ensure environment consistency
    res = subprocess.run([sys.executable, "verify_system.py"])
    if res.returncode != 0:
        print("\n❌ 系统自检未通过！请修正配置后重试。")
        sys.exit(1)
    print("✅ 系统自检通过，准备启动服务...")

def run_initial_sync():
    db_file = BASE_DIR / "data" / "emails.db"
    if not db_file.exists():
        print("\n📦 正在初始化数据库并进行首次同步 (请稍候)...")
    else:
        print("\n🔄 正在同步最新邮件...")
    
    subprocess.run([sys.executable, "tools/fetch_emails.py", "--max-scan", "50"])

def start_background_process(script_path, log_file, pid_file):
    """跨平台启动后台进程"""
    if not LOGS_DIR.exists():
        LOGS_DIR.mkdir()

    log_fh = open(log_file, "w", encoding="utf-8")
    
    # 在 Windows 上，我们可能需要使用不同的启动方式来模拟 "nohup"
    creation_flags = 0
    if sys.platform == "win32":
        # CREATE_NEW_PROCESS_GROUP or something? 
        # Actually, for most users just Popen is fine if the script stays alive
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    # subprocess.Popen(..., start_new_session=True) is for Unix
    popen_kwargs = {
        "stdout": log_fh,
        "stderr": subprocess.STDOUT,
        "bufsize": 1,
        "universal_newlines": True,
        "cwd": str(BASE_DIR)
    }
    
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True
    else:
        popen_kwargs["creationflags"] = creation_flags

    process = subprocess.Popen([sys.executable, "-u", script_path], **popen_kwargs)
    
    with open(pid_file, "w") as f:
        f.write(str(process.pid))
    
    return process.pid

def main():
    print_header("🚀 DeepMail AI 启动程序 (Cross-Platform)", "blue")
    
    setup_env()
    run_self_check()
    run_initial_sync()
    
    # 启动后端
    print("\n📂 正在启动 Dashboard 后端...")
    api_pid = start_background_process("api_main.py", LOGS_DIR / "api.log", API_PID_FILE)
    print(f"✅ 后端已启动 (PID: {api_pid})")

    # 启动调度器
    print("⏰ 正在启动 自动同步调度器...")
    sched_pid = start_background_process("tools/scheduler.py", LOGS_DIR / "scheduler.log", SCHEDULER_PID_FILE)
    print(f"✅ 调度器已启动 (PID: {sched_pid})")

    print(f"\n🌐 正在为您打开 Dashboard 界面...")
    time.sleep(2)
    webbrowser.open("http://localhost:8000")

    print("-" * 40)
    print("✨ 全部服务已在后台启动！")
    print("🔗 访问地址: http://localhost:8000")
    print("📝 停止服务请运行: python stop_service.py")
    print("=======================================")

if __name__ == "__main__":
    main()
