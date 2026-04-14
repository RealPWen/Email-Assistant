import os
import sys
import time
import json
import sqlite3
from tools.utils import (
    BASE_DIR, decode_str, normalize_date, smart_translate, 
)
from core.db_manager import DBManager
from core.email_summary_skill import EmailSummarySkill

# 确保项目根目录在搜索路径中
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

def backfill():
    """补全数据 (翻译 + 标准化时间 + AI 分析)"""
    db = DBManager()
    print("🔍 正在查找数据不全的存量邮件...")
    unprocessed = db.get_untranslated_emails()
    if not unprocessed:
        print("✨ 数据已完整。")
        return

    print(f"🚀 处理 {len(unprocessed)} 封邮件...")
    ai_skill = EmailSummarySkill()
    for idx, (m_id, body, date_str, norm_date, summary, category) in enumerate(unprocessed, 1):
        try:
            target_norm_date = norm_date if norm_date and norm_date != 'NULL' else normalize_date(date_str)
            target_translation = smart_translate(body) if body else None
            
            target_ai_data = None
            if not summary or not category or category == '其他':
                ai_res = ai_skill.analyze_email(body)
                target_ai_data = {
                    "summary": ai_res.get("summary", ""),
                    "action_items": json.dumps(ai_res.get("action_items", []), ensure_ascii=False),
                    "importance": ai_res.get("importance", "低"),
                    "category": ai_res.get("category", "其他")
                }
            db.update_email_metadata(m_id, target_norm_date, target_translation, target_ai_data)
            print(f"[{idx}/{len(unprocessed)}] ✅ 更新: {m_id[:15]}")
        except Exception as e:
            print(f"❌ 失败: {e}")

def clean_ids():
    """清洗 Message-ID 中的编码噪音"""
    db = DBManager()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, message_id FROM emails")
        rows = cursor.fetchall()
        for r_id, old_id in rows:
            if not old_id: continue
            new_id = decode_str(old_id)
            if new_id != old_id:
                try:
                    cursor.execute("UPDATE emails SET message_id = ? WHERE id = ?", (new_id, r_id))
                except sqlite3.IntegrityError:
                    cursor.execute("DELETE FROM emails WHERE id = ?", (r_id,))
        conn.commit()
    print("✨ ID 清洗完成。")

def reclassify():
    """重新分类所有 '其他' 类别的邮件"""
    db = DBManager()
    ai_skill = EmailSummarySkill()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT message_id, body FROM emails WHERE category = '其他'")
        others = cursor.fetchall()
    
    for idx, (m_id, body) in enumerate(others, 1):
        try:
            ai_res = ai_skill.analyze_email(body)
            db.update_email_metadata(m_id, ai_data=ai_res)
            print(f"[{idx}/{len(others)}] ✅ 重分类完成")
        except Exception as e:
            print(f"❌ 失败: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DeepMail Maintenance Tools")
    parser.add_argument("action", choices=["backfill", "clean_ids", "reclassify"])
    args = parser.parse_args()
    
    if args.action == "backfill": backfill()
    elif args.action == "clean_ids": clean_ids()
    elif args.action == "reclassify": reclassify()
