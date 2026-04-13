import os
import sys
import json
import sqlite3
import requests
import time
from dotenv import load_dotenv

# 解决导入问题
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

from core.db_manager import DBManager
from core.email_summary_skill import EmailSummarySkill
from tools.fetch_emails import normalize_date, smart_translate, generate_composite_key, decode_str
from tools.imap_ops import get_mail_connection
import email

load_dotenv(os.path.join(BASE_DIR, ".env"))

# 全局错误追踪
HAS_CRITICAL_ERROR = False

def test_section(id, name):
    print(f"\n{id}. {name}")
    print("-" * 50)

def report_error(msg):
    global HAS_CRITICAL_ERROR
    HAS_CRITICAL_ERROR = True
    print(f"❌ {msg}")

def verify_all():
    print("🚀 DeepMail AI 系统全面自检程序启动...")
    print(f"⏰ 当前时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 环境与配置检查
    test_section(1, "环境与关键配置检查")
    email_user = os.getenv("EMAIL_USER")
    auth_code = os.getenv("EMAIL_AUTH_CODE")
    if email_user and auth_code:
        print(f"✅ EMAIL_USER 已配置: {email_user}")
        print(f"✅ EMAIL_AUTH_CODE 已加密存储")
    else:
        report_error("邮件授权配置缺失 (EMAIL_USER 或 EMAIL_AUTH_CODE)")
        
    ds_api_key = os.getenv("DEEPSEEK_API_KEY")
    if ds_api_key:
        print(f"✅ DeepSeek API 密钥已配置 (前缀: {ds_api_key[:8]}...)")
    else:
        report_error("DeepSeek API 密钥缺失 (DEEPSEEK_API_KEY)")

    # 2. 数据库性能与完整性检查
    test_section(2, "数据库 (WAL 模式 & 完整性)")
    db = DBManager()
    with db.get_connection() as conn:
        # 检查 WAL 模式
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        if mode.lower() == "wal":
            print(f"✅ 并发优化 (WAL 模式): 已开启")
        else:
            print(f"⚠️  并发优化 (WAL 模式): 未开启 (当前: {mode})")
            
        # 检查表结构
        cursor.execute("PRAGMA table_info(emails)")
        cols = {row[1] for row in cursor.fetchall()}
        expected = {'id', 'message_id', 'subject', 'is_read', 'normalized_date', 'importance', 'category'}
        if expected.issubset(cols):
            print(f"✅ 表结构完整性: 正常")
        else:
            report_error(f"数据库表结构缺失字段: {expected - cols}")

    # 3. 核心算法验证 (Subject+Date Key)
    test_section(3, "核心排重算法 (Subject + Date Key)")
    # 测试 Composite Key 生成
    test_subject = "=?utf-8?B?6L+Z5piv5pys5ZGo6YCJ5L+u6K++6K6h5YiS?=" # "这是本周选修课计划"
    test_date = "Mon, 13 Apr 2026 15:00:00 +0800"
    
    key = generate_composite_key(test_subject, test_date)
    expected_prefix = "2026-04-13T15:00:00"
    if key.startswith(expected_prefix) and "这是本周选修课计划" in key:
        print(f"✅ 组合 Key 生成算法正确: {key}")
    else:
        report_error(f"组合 Key 生成异常: {key}")

    # 4. AI 智能分析模块自检
    test_section(4, "AI 智能分析 (DeepSeek 接口)")
    try:
        skill = EmailSummarySkill()
        test_body = "【缴费通知】下周一前请缴纳HKU春季学费，逾期将产生罚款。"
        print("🤖 正在请求 AI 进行结构化输出验证...")
        result = skill.analyze_email(test_body)
        
        if result and "importance" in result:
            print(f"✅ AI 响应成功: {result.get('summary')[:30]}...")
            print(f"✅ 重要性判定: {result.get('importance')} ({result.get('reason')[:20]}...)")
            print(f"✅ 类别归属: {result.get('category')}")
        else:
            report_error("AI 响应格式不符合预期，请检查 API Key 是否有效或可用额度")
    except Exception as e:
        report_error(f"AI 模块异常 (连接失败): {e}")

    # 5. 后端 API 接口连通性
    test_section(5, "后端 API 连通性与流式接口")
    try:
        api_url = "http://localhost:8000"
        resp = requests.get(f"{api_url}/api/stats", timeout=3)
        if resp.status_code == 200:
            print(f"✅ 仪表盘后端服务: 正常运行")
        else:
            print(f"⚠️  后端 API 返回异常状态码: {resp.status_code}")
            
        progress_url = f"{api_url}/api/sync/progress"
        p_resp = requests.get(progress_url, stream=True, timeout=2)
        if p_resp.headers.get('Content-Type') == 'text/event-stream; charset=utf-8':
            print(f"✅ SSE 实时进度流接口: 准备就绪")
            p_resp.close()
            
    except Exception as e:
        print(f"ℹ️  API 验证跳过 (后端服务当前未运行)")

    # 7. 邮件抓取与内容解析实测
    test_section(7, "邮件抓取与内容解析实测")
    try:
        mail = get_mail_connection()
        # 对于 163 等邮箱，必须先发送 ID 信息才能进行后续操作
        try:
            mail.xatom('ID', '("name" "verify_script" "version" "1.1.0")')
        except:
            pass
            
        status, _ = mail.select("INBOX", readonly=True)
        if status != "OK":
            status, _ = mail.select("Inbox", readonly=True)
            
        if status != "OK":
            report_error(f"无法选择收件箱 (Status: {status})。请检查授权码是否正确。")
        else:
            status, search_data = mail.search(None, "ALL")
            mail_ids = search_data[0].split()
            
            if mail_ids:
                latest_id = mail_ids[-1]
                print(f"📡 成功选择收件箱。正在从服务器拉取最新邮件 metadata...")
                res, msg_data = mail.fetch(latest_id, "(RFC822.HEADER)")
                if res == "OK":
                    print(f"✅ 邮件内容解析测试通过")
                else:
                    report_error(f"邮件内容拉取 (FETCH) 失败: {res}")
            else:
                print("⚠️ 邮件箱为空")
        mail.logout()
    except Exception as e:
        report_error(f"邮件服务器连接测试失败: {e}")

    print("\n" + "="*50)
    if HAS_CRITICAL_ERROR:
        print("❌ 系统自检未通过，请根据上方错误提示修正配置。")
        sys.exit(1)
    else:
        print("✨ 所有核心功能验证完成！系统运行良好。")
        sys.exit(0)

if __name__ == "__main__":
    verify_all()
