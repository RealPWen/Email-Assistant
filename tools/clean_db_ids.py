import os
import sqlite3
import imaplib
import email
from email.header import decode_header

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data/emails.db")

def decode_str(s):
    """解码邮件头字段 (复用逻辑)"""
    if not s: return ""
    try:
        decoded_parts = decode_header(s)
        result = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result += part.decode(encoding if encoding else "utf-8", "ignore")
            else:
                result += part
        return result.strip()
    except:
        return str(s).strip()

def clean_ids():
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库不存在: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("🔍 正在读取数据库中的 Message-ID...")
    cursor.execute("SELECT id, message_id FROM emails")
    rows = cursor.fetchall()
    
    updated_count = 0
    conflict_count = 0
    
    for row_id, old_id in rows:
        if not old_id: continue
        
        # 1. 解码 (处理被错误存入的 =?UTF-8?B?...?)
        # 2. 去空格换行
        new_id = decode_str(old_id)
        
        if new_id != old_id:
            try:
                # 尝试更新为清洗后的 ID
                cursor.execute("UPDATE emails SET message_id = ? WHERE id = ?", (new_id, row_id))
                updated_count += 1
            except sqlite3.IntegrityError:
                # 如果清洗后的 ID 已经存在于另一行，则说明这行是由于 Bug 产生的重复“鬼影”
                # 我们删除这行多余的
                print(f"  ⚠️ 发现冲突 ID (重复邮件)，删除冗余记录 ID: {row_id}")
                cursor.execute("DELETE FROM emails WHERE id = ?", (row_id,))
                conflict_count += 1
    
    conn.commit()
    conn.close()
    print(f"\n✨ 数据库清洗完成！")
    print(f"✅ 修正了 {updated_count} 个 Message-ID")
    print(f"🗑️ 删除了 {conflict_count} 条冗余重复记录")

if __name__ == "__main__":
    clean_ids()
