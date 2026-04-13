import os
import sys
import json
import sqlite3
from dotenv import load_dotenv

# 解决导入问题
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from core.db_manager import DBManager
from core.email_summary_skill import EmailSummarySkill

def fix_financial_importance():
    db = DBManager()
    skill = EmailSummarySkill()
    
    print("🔍 正在查找被误标为‘低重要性’的财务或重要邮件...")
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        # 扫描所有标记为“低”的邮件，看是否有被漏掉的符合新画像的高价值内容
        cursor.execute("""
            SELECT id, message_id, subject, body, category, importance 
            FROM emails 
            WHERE importance = '低'
            ORDER BY id DESC LIMIT 100
        """)
        rows = cursor.fetchall()
        
        if not rows:
            print("✨ 没有发现需要修复的邮件。")
            return

        print(f"🚀 发现 {len(rows)} 封可能需要重新评估的邮件。正在处理...")
        
        for email_id, m_id, subject, body, cat, imp in rows:
            print(f"📝 重新评估: {subject[:40]}...")
            
            # 使用最新的 Prompt 进行分析
            result = skill.analyze_email(body)
            
            if result and result.get('importance') != imp:
                print(f"   ✅ 重要性更新: {imp} -> {result.get('importance')} (分类: {result.get('category')})")
                
                cursor.execute("""
                    UPDATE emails 
                    SET importance = ?, category = ?, summary = ?, reason = ? 
                    WHERE id = ?
                """, (result.get('importance'), result.get('category'), result.get('summary'), result.get('reason'), email_id))
            else:
                print(f"   ℹ️ 维持原判: {imp}")
    
    print("\n✨ 修复完成！请刷新网页查看。")

if __name__ == "__main__":
    fix_financial_importance()
