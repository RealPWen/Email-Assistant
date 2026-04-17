import os
import sys
import subprocess
import time
import webbrowser
import getpass
from pathlib import Path
import requests

from tools.utils import (
    BASE_DIR, LOGS_DIR, ENV_FILE, API_PID_FILE, SCHEDULER_PID_FILE, print_header, get_local_ip
)

def check_dependencies():
    """检查必要的库是否已安装。"""
    required = ["fastapi", "uvicorn", "requests", "dotenv", "bs4", "deep_translator"]
    missing = []
    for lib in required:
        try:
            if lib == "dotenv":
                import dotenv
            elif lib == "bs4":
                import bs4
            else:
                __import__(lib)
        except ImportError:
            missing.append(lib)
    
    if missing:
        print_header("⚠️  缺少必要的运行环境", "red")
        print(f"以下库未安装: {', '.join(missing)}")
        print("\n请运行以下命令进行安装:")
        print("pip install -r requirements.txt")
        print("-" * 40)
        sys.exit(1)

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
    script_path = str(BASE_DIR / "tools" / "verify_system.py")
    
    # Pass current PYTHONPATH to ensure sub-scripts can find 'core' and 'tools'
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)
    
    res = subprocess.run([sys.executable, script_path], env=env)
    if res.returncode != 0:
        print("\n❌ 系统自检未通过！请修正配置后重试。")
        sys.exit(1)
    print("✅ 系统自检通过，准备启动服务...")

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

    # 正确处理脚本路径
    full_script_path = str(BASE_DIR / script_path.replace("/", os.sep))
    
    # 注入 PYTHONPATH
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)
    popen_kwargs["env"] = env

    process = subprocess.Popen([sys.executable, "-u", full_script_path], **popen_kwargs)
    
    with open(pid_file, "w") as f:
        f.write(str(process.pid))
    
    return process.pid

def wait_for_api_ready(url="http://localhost:8000/api/stats", timeout=20):
    """等待 API 真正可用，避免浏览器打开过早导致首页首次请求失败。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=1.5)
            if response.ok:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.5)
    return False

def main():
    check_dependencies()
    print_header("🚀 DeepMail AI 启动程序 (Cross-Platform)", "blue")
    
    while True:
        setup_env()
        try:
            run_self_check()
            # 如果自检通过，跳出配置循环
            break
        except SystemExit:
            print("\n" + "!" * 40)
            print("⚠️ 系统探测到配置信息（邮箱或授权码）可能不正确。")
            choice = input("是否要【重新输入】配置信息？(y/n): ").lower()
            if choice == 'y':
                if ENV_FILE.exists():
                    ENV_FILE.unlink() # 删除旧文件以触发重新配置
                continue
            else:
                print("❌ 程序退出。请手动检查 .env 文件。")
                sys.exit(1)

    # 启动后端
    print("\n📂 正在启动 Dashboard 后端...")
    api_pid = start_background_process("app/server.py", LOGS_DIR / "api.log", API_PID_FILE)
    print(f"✅ 后端已启动 (PID: {api_pid})")

    # 启动调度器
    print("⏰ 正在启动 自动同步调度器...")
    sched_pid = start_background_process("tools/scheduler.py", LOGS_DIR / "scheduler.log", SCHEDULER_PID_FILE)
    print(f"✅ 调度器已启动 (PID: {sched_pid})")

    print("\n⚡ 首次同步已改为后台执行，网页会先打开，邮件与 AI 摘要将逐步出现。")
    print("⏳ 正在等待 Dashboard API 就绪...")
    api_ready = wait_for_api_ready()
    if api_ready:
        print("✅ Dashboard API 已就绪。")
    else:
        print("⚠️ API 启动较慢，先尝试打开网页；页面会自动重试加载邮件。")

    print(f"\n🌐 正在为您打开 Dashboard 界面...")
    webbrowser.open("http://localhost:8000")

    print("-" * 40)
    print("✨ 全部服务已在后台启动！")
    
    local_ip = get_local_ip()
    print(f"🔗 本地访问: http://localhost:8000")
    if local_ip != "127.0.0.1":
        print(f"🌍 局域网访问: http://{local_ip}:8000 (同一 WiFi 下可用)")
        
    print("📝 停止服务请运行: python stop.py")
    print("=======================================")

if __name__ == "__main__":
    main()
