import sqlite3
import sys
import os

# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "emails.db")

def query_emails(keyword=None):
    if not os.path.exists(DB_PATH):
        print(f"❌ 找不到数据库文件: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if keyword:
        print(f"🔍 正在检索关键词: '{keyword}'...")
        cursor.execute('''
            SELECT id, date_str, sender, subject 
            FROM emails 
            WHERE subject LIKE ? OR body LIKE ? 
            ORDER BY id DESC
        ''', (f'%{keyword}%', f'%{keyword}%'))
    else:
        print("📋 列出库中最近的 10 封邮件：")
        cursor.execute('''
            SELECT id, date_str, sender, subject 
            FROM emails 
            ORDER BY id DESC 
            LIMIT 10
        ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("📭 没有找到匹配的邮件。")
        return

    print("-" * 80)
    for row in rows:
        email_id, date, sender, subject = row
        print(f"[{email_id}] {date}")
        print(f"   👤 发件人: {sender}")
        print(f"   📝 主题: {subject}")
        print("-" * 80)

if __name__ == "__main__":
    search_term = sys.argv[1] if len(sys.argv) > 1 else None
    query_emails(search_term)
