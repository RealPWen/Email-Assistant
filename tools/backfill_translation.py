import os
import sys
import time
import random

# 解决导入问题
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from core.db_manager import DBManager
from core.email_summary_skill import EmailSummarySkill
from tools.fetch_emails import smart_translate, normalize_date
import json

def backfill_data():
    """补全数据库中存量邮件的数据 (翻译 + 标准化时间)"""
    db = DBManager()
    
    print("🔍 正在查找数据不全的存量邮件...")
    unprocessed = db.get_untranslated_emails()
    total = len(unprocessed)
    
    if total == 0:
        print("✨ 所有邮件数据已完整。")
        return

    print(f"🚀 发现 {total} 封待处理邮件，准备开始...\n")
    
    update_count = 0
    start_time = time.time()
    
    for idx, (msg_id, body, date_str, norm_date, summary, category) in enumerate(unprocessed, 1):
        try:
            target_norm_date = norm_date
            target_translation = None
            target_ai_data = None
            
            # 1. 修复时间标准化
            if not norm_date or norm_date == 'NULL':
                target_norm_date = normalize_date(date_str)
            
            # 2. 处理翻译和 AI 分析
            if body and body.strip():
                print(f"[{idx}/{total}] ⚙️ 处理 ID: {msg_id[:15]}...")
                
                # 如果没有翻译，进行翻译
                # 注意：db 查询已经通过 WHERE 过滤，但这里我们检查返回的 body_translation 是否已存在
                # 在此脚本逻辑中，如果是全新补全，translation 必做
                if True: # 保持逻辑简单，交给 update_email_metadata 过滤
                    print(f"   📝 正在翻译正文...")
                    target_translation = smart_translate(body)
                
                # 如果没有 AI 摘要或尚未分类，进行 AI 分析
                if not summary or not category or category == '其他':
                    print(f"   🤖 AI 正在智能分析 (摘要/待办/重要性/分类)...")
                    ai_skill = EmailSummarySkill()
                    ai_res = ai_skill.analyze_email(body)
                    target_ai_data = {
                        "summary": ai_res.get("summary", ""),
                        "action_items": json.dumps(ai_res.get("action_items", []), ensure_ascii=False),
                        "importance": ai_res.get("importance", "低"),
                        "category": ai_res.get("category", "其他")
                    }
            
            # 执行数据库更新
            db.update_email_metadata(msg_id, target_norm_date, target_translation, target_ai_data)
            update_count += 1
            
            # 进度报告与 ETA
            elapsed = time.time() - start_time
            avg_time = elapsed / idx
            remaining = avg_time * (total - idx)
            eta_str = f"{remaining:.1f}s" if remaining < 60 else f"{remaining/60:.1f}m"
            
            print(f"   ✅ 已同步更新 | 剩余预估: {eta_str}")
            
            # 只有在做了翻译的情况下才增加随机延迟
            if target_translation:
                time.sleep(random.uniform(0.5, 1.2))
                
        except Exception as e:
            print(f"   ❌ 处理失败 (ID: {msg_id}): {e}")
            time.sleep(2)

    print(f"\n✨ 补全结束！成功同步更新: {update_count} 封邮件")

if __name__ == "__main__":
    backfill_data()
