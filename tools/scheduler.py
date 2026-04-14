import os
import sys
import time
import argparse
from datetime import datetime

# 解决导入问题
# 解决导入问题
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from tools.fetch_emails import sync_emails

def run_scheduler(interval_minutes=10):
    """
    轻量级调度器：每隔指定时间自动同步一次邮件。
    """
    print(f"🚀 DeepMail AI 自动同步服务已启动...")
    print(f"⏰ 设定同步间隔: {interval_minutes} 分钟")
    print(f"📅 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)

    try:
        while True:
            current_time = datetime.now().strftime("%H:%M:%S")
            print(f"\n🔄 [{current_time}] 正在检查新邮件...")
            
            # 执行同步逻辑
            # 我们限制 max_scan 为 200，提高增量同步效率
            sync_emails(max_scan=200, batch_size=10)
            
            print(f"😴 同步结束。等待 {interval_minutes} 分钟进行下一次检查...")
            time.sleep(interval_minutes * 60)
            
    except KeyboardInterrupt:
        print(f"\n🛑 服务已停止。")
    except Exception as e:
        print(f"⚠️ 调度器发生异常: {e}")
        # 如果崩溃，等待 60 秒后重试
        time.sleep(60)
        run_scheduler(interval_minutes)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DeepMail AI 自动同步调度器")
    parser.add_argument("--interval", type=int, default=10, help="同步间隔（分钟），默认 10 分钟")
    args = parser.parse_args()
    
    run_scheduler(args.interval)
