import os
import sys
import signal
from pathlib import Path

from tools.utils import API_PID_FILE, SCHEDULER_PID_FILE, print_header

def kill_process(pid_file, name):
    if not pid_file.exists():
        print(f"ℹ️ 未发现运行中的 {name} PID 文件。")
        return

    try:
        with open(pid_file, "r") as f:
            pid = int(f.read().strip())
        
        print(f"正在停止 {name} (PID: {pid})...")
        
        if sys.platform == "win32":
            # Windows: use taskkill to be sure
            os.system(f"taskkill /F /PID {pid}")
        else:
            # Unix: use os.kill
            os.kill(pid, signal.SIGTERM)
            
        pid_file.unlink() # Delete file
        print(f"✅ {name} 已停止。")
    except Exception as e:
        print(f"⚠️ 停止 {name} 失败: {e}")
        if pid_file.exists():
            pid_file.unlink()

def main():
    print_header("🛑 正在停止 DeepMail AI 服务...", "red")
    
    kill_process(API_PID_FILE, "API 服务")
    kill_process(SCHEDULER_PID_FILE, "调度器服务")
    
    print("-" * 40)
    print("✨ 所有后台进程已尝试关闭。")
    print("=======================================")

if __name__ == "__main__":
    main()
