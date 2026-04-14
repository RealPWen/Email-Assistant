import os
import imaplib
import email
import time
import json
import re
import concurrent.futures
import sys

# 解决导入问题，确保能从根目录导入
# 解决导入问题，确保能从根目录导入
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from tools.utils import (
    decode_str, normalize_date, generate_composite_key,
    smart_translate, chunk_list,
)
from dotenv import load_dotenv

# 使用绝对路径定位 .env
load_dotenv(os.path.join(BASE_DIR, ".env"))

from core.db_manager import DBManager
from core.email_summary_skill import EmailSummarySkill


def get_text_from_msg(msg):
    """从邮件对象中提取纯文本内容。"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                payload = part.get_payload(decode=True)
                if payload:
                    body += payload.decode(part.get_content_charset() or "utf-8", "ignore")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", "ignore")
    return body.strip()


def get_attachments_metadata(msg):
    """提取附件元数据（不下载内容）。"""
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            if "attachment" in str(part.get("Content-Disposition")):
                payload = part.get_payload(decode=True)
                attachments.append({
                    "name": decode_str(part.get_filename()) or "unnamed",
                    "size": len(payload) if payload else 0,
                    "type": part.get_content_type()
                })
    return attachments


def parse_flags(flags_bytes):
    return 1 if "\\SEEN" in str(flags_bytes).upper() else 0


def sync_emails(max_scan=500, batch_size=50, progress_callback=None):
    """高度优化的邮件同步：支持批量抓取、元数据提取和状态同步。"""

    def report(status, message, progress=0, details=None):
        info = {"status": status, "message": message, "progress": progress, "details": details or {}}
        if progress_callback:
            progress_callback(info)
        print(f"[{status}] {message}")

    report("start", "正在初始化同步任务...", 5)
    db = DBManager()
    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_AUTH_CODE")
    imap_server = "imap.163.com"

    if not email_user or not email_pass:
        print("❌ 错误: 请确保 .env 文件中配置了 EMAIL_USER 和 EMAIL_AUTH_CODE")
        return

    try:
        print(f"📡 正在连接 {imap_server}...")
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_user, email_pass)
        try:
            mail.xatom('ID', '("name" "fetch_script" "version" "1.1.0")')
        except Exception as e:
            print(f"⚠️ IMAP ID 指令不受支持或失败: {e}")

        mail.select("INBOX")
        status, messages = mail.search(None, "ALL")
        mail_ids = messages[0].split()
        total_found = len(mail_ids)

        report("scanning", f"连接成功。正在扫描服务器 (共 {total_found} 封)...", 10)

        scan_ids = mail_ids[max(0, total_found - max_scan):]
        scan_ids.reverse()

        ids_to_fetch_full = []
        status_updated_count = 0

        # 第一阶段：增量扫描 & 状态同步
        for chunk in chunk_list(scan_ids, 50):
            id_range = ",".join([id.decode() for id in chunk])
            res, data = mail.fetch(id_range, "(FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT DATE)])")

            for i in range(0, len(data), 2):
                if not isinstance(data[i], tuple):
                    continue
                header_data = data[i][1]
                meta_str = data[i][0].decode()
                is_read = parse_flags(meta_str)

                try:
                    m_id_match = re.search(r'^(\d+)', meta_str)
                    m_id = m_id_match.group(1) if m_id_match else chunk[i // 2].decode()
                except Exception:
                    m_id = chunk[i // 2].decode()

                headers = email.message_from_bytes(header_data)
                sync_id = generate_composite_key(headers.get("Subject"), headers.get("Date"))

                if db.exists(sync_id):
                    db.update_email_status(sync_id, is_read)
                    status_updated_count += 1
                else:
                    report("debug", f"发现新邮件 ID: [{sync_id}]")
                    ids_to_fetch_full.append((m_id, sync_id, is_read))

        total_to_sync = len(ids_to_fetch_full)
        report("scanned", f"扫描完成。发现 {total_to_sync} 封新邮件，{status_updated_count} 封已更新状态。", 20)

        if total_to_sync == 0:
            report("done", "没有发现新邮件。", 100)
            mail.close(); mail.logout()
            return

        report("fetching", f"正在抓取新邮件内容 (共 {total_to_sync} 封)...", 25)

        # 第二阶段：批量 Fetch + 并行 AI 分析
        new_count = 0

        def process_single_email(email_data):
            subject = email_data["subject"]
            body = email_data["body"]
            print(f"   📝 [并行] 翻译+分析: {subject[:20]}...")
            email_data["body_translation"] = smart_translate(body)
            try:
                ai_result = EmailSummarySkill().analyze_email(body)
            except Exception as e:
                print(f"   ⚠️ AI 分析失败: {e}")
                ai_result = {}
            email_data["summary"] = ai_result.get("summary", "")
            email_data["action_items"] = json.dumps(ai_result.get("action_items", []), ensure_ascii=False)
            email_data["importance"] = ai_result.get("importance", "低")
            return email_data

        for idx_batch, batch in enumerate(chunk_list(ids_to_fetch_full, batch_size), 1):
            batch_uids = ",".join([item[0] for item in batch])
            res, msg_data_list = mail.fetch(batch_uids, "(RFC822)")

            parsed_emails = []
            for i in range(0, len(msg_data_list), 2):
                if not isinstance(msg_data_list[i], tuple):
                    continue
                msg = email.message_from_bytes(msg_data_list[i][1])
                subject = decode_str(msg.get("Subject"))
                sender = decode_str(msg.get("From"))
                date_str = msg.get("Date")

                try:
                    m_id_match = re.search(r'^(\d+)', msg_data_list[i][0].decode())
                    current_m_id = m_id_match.group(1) if m_id_match else None
                except Exception:
                    current_m_id = None

                # 匹配元数据
                target_sync_id, target_is_read = None, 0
                for b_item in batch:
                    if b_item[0] == current_m_id:
                        target_sync_id, target_is_read = b_item[1], b_item[2]
                        break
                if not target_sync_id:
                    computed = generate_composite_key(msg.get("Subject"), date_str)
                    for b_item in batch:
                        if b_item[1] == computed:
                            target_sync_id, target_is_read = b_item[1], b_item[2]
                            break
                    if not target_sync_id:
                        target_sync_id = computed

                parsed_emails.append({
                    "message_id": target_sync_id,
                    "subject": subject, "sender": sender, "date_str": date_str,
                    "normalized_date": normalize_date(date_str),
                    "body": get_text_from_msg(msg), "folder": "INBOX",
                    "is_read": target_is_read,
                    "attachments_metadata": json.dumps(get_attachments_metadata(msg), ensure_ascii=False),
                    "body_translation": "", "summary": "", "action_items": "[]", "importance": "低",
                })

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                processed = list(executor.map(process_single_email, parsed_emails))

            for ed in processed:
                if db.save_email(ed):
                    new_count += 1

            done_count = min(idx_batch * batch_size, total_to_sync)
            progress = 25 + int((done_count / total_to_sync) * 70)
            last_subj = processed[-1]["subject"] if processed else "未知"
            report("analyzing", f"AI 正在分析邮件批量 ({done_count}/{total_to_sync})...", progress,
                   {"current": done_count, "total": total_to_sync, "last_subject": last_subj})

        mail.close(); mail.logout()
        report("done", f"同步完成！新增 {new_count} 封邮件。", 100, {"new_count": new_count})

    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback; traceback.print_exc()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DeepMail Email Fetcher")
    parser.add_argument("--max-scan", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    sync_emails(max_scan=args.max_scan, batch_size=args.batch_size)
