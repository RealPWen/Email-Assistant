import os
import sys
import time
import json

# 解决导入问题
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from core.db_manager import DBManager
from core.email_summary_skill import EmailSummarySkill

def reclassify_others():
    """专门针对标记为 '其他' 的邮件进行重新分类和摘要生成的脚本"""
    db = DBManager()
    ai_skill = EmailSummarySkill()
    
    print("🔍 正在查找分类为 '其他' 的邮件...")
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT message_id, body, subject FROM emails WHERE category = '其他'")
        others = cursor.fetchall()
    
    total = len(others)
    if total == 0:
        print("✨ 没有需要重新分类的邮件。")
        return

    print(f"🚀 发现 {total} 封分类为 '其他' 的邮件，准备使用 API 重新分类...\n")
    
    update_count = 0
    start_time = time.time()
    
    for idx, (msg_id, body, subject) in enumerate(others, 1):
        try:
            print(f"[{idx}/{total}] ⚙️ 正在重新处理: {subject[:30]}...")
            
            # 调用最新的 AI 逻辑 (API 优先)
            ai_res = ai_skill.analyze_email(body)
            
            target_ai_data = {
                "summary": ai_res.get("summary", ""),
                "action_items": json.dumps(ai_res.get("action_items", []), ensure_ascii=False),
                "importance": ai_res.get("importance", "低"),
                "category": ai_res.get("category", "其他")
            }
            
            # 更新数据库
            db.update_email_metadata(msg_id, ai_data=target_ai_data)
            update_count += 1
            
            # 控制速度，避免 API 频率限制
            print(f"   ✅ 分类成功: {target_ai_data['category']}")
            
        except Exception as e:
            print(f"   ❌ 处理失败 (Subject: {subject[:20]}): {e}")

    print(f"\n✨ 批量重新分类结束！成功更新: {update_count} 封邮件")

if __name__ == "__main__":
    reclassify_others()
