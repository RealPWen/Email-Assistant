import os
import sys
import imaplib
import email
import time
import json
from email.header import decode_header
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv
from deep_translator import GoogleTranslator

# 解决导入问题
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from core.db_manager import DBManager
from core.email_summary_skill import EmailSummarySkill

# 加载 .env 配置文件
load_dotenv(os.path.join(BASE_DIR, ".env"))

def get_text_from_msg(msg):
    """从邮件对象中提取纯文本内容"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body += payload.decode(charset, "ignore")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, "ignore")
    return body.strip()

def get_attachments_metadata(msg):
    """提取附件元数据（不下载内容）"""
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition"))
            if "attachment" in content_disposition:
                filename = decode_str(part.get_filename())
                content_type = part.get_content_type()
                # 估算大小 (base64 编码通常比原文件大 33% 左右，这里取解析后的字节数)
                payload = part.get_payload(decode=True)
                size = len(payload) if payload else 0
                
                attachments.append({
                    "name": filename or "unnamed",
                    "size": size,
                    "type": content_type
                })
    return attachments

def decode_str(s):
    """解码邮件头字段"""
    if not s:
        return ""
    try:
        decoded_parts = decode_header(s)
        result = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result += part.decode(encoding if encoding else "utf-8", "ignore")
            else:
                result += part
        return result
    except:
        return str(s)

def normalize_date(date_str):
    """将邮件日期转换为标准 ISO 格式"""
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except Exception:
        return None

def smart_translate(text, target='zh-CN', chunk_limit=4500):
    """
    智能翻译：支持长文本分段翻译，按段落截断。
    """
    if not text or not text.strip():
        return ""
    
    try:
        translator = GoogleTranslator(source='auto', target=target)
        
        # 如果文本较短，直接翻译
        if len(text) <= chunk_limit:
            return translator.translate(text)
        
        # 长文本处理：按段落切割
        paragraphs = text.split('\n')
        chunks = []
        current_chunk = ""
        
        for p in paragraphs:
            # 如果单段就超过了限制（极少见），强制按字符切分
            if len(p) > chunk_limit:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                # 强制切分长段落
                for i in range(0, len(p), chunk_limit):
                    chunks.append(p[i:i+chunk_limit])
                continue

            if len(current_chunk) + len(p) + 1 <= chunk_limit:
                current_chunk += p + "\n"
            else:
                chunks.append(current_chunk.strip())
                current_chunk = p + "\n"
        
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        # 分块翻译并合并
        translated_chunks = []
        for i, chunk in enumerate(chunks):
            if chunk.strip():
                translated_chunks.append(translator.translate(chunk))
        
        return "\n".join(translated_chunks)
    except Exception as e:
        print(f"⚠️ 翻译失败: {e}")
        return ""

def parse_flags(flags_bytes):
    """解析 IMAP FLAGS，返回是否为已读 (1/0)"""
    flags_str = str(flags_bytes).upper()
    return 1 if "\\SEEN" in flags_str else 0

def generate_composite_key(subject, date_str):
    """根据主题和日期生成稳定的唯一标识码"""
    # 规范化日期
    norm_date = normalize_date(date_str) or "unknown_date"
    # 解码并规范化主题 (去除两端空格，并限制长度防止过长)
    norm_subject = decode_str(subject).strip()
    return f"{norm_date}_{norm_subject}"

def chunk_list(lst, n):
    """将列表切分为大小为 n 的块"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def sync_emails(max_scan=500, batch_size=20, progress_callback=None):
    """
    高度优化的邮件同步：支持批量抓取、元数据提取和状态同步。
    :param progress_callback: 回调函数，接收 dict 格式的进度信息
    """
    def report(status, message, progress=0, details=None):
        if progress_callback:
            progress_callback({
                "status": status,
                "message": message,
                "progress": progress,
                "details": details or {}
            })
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
        mail.xatom('ID', '("name" "fetch_script" "version" "1.1.0")')
        mail.select("INBOX")

        status, messages = mail.search(None, "ALL")
        mail_ids = messages[0].split()
        total_found = len(mail_ids)
        
        report("scanning", f"连接成功。正在扫描服务器 (共 {total_found} 封)...", 10)
        
        # 确定扫描范围 (从最后往前扫描)
        scan_ids = mail_ids[max(0, total_found - max_scan):total_found]
        scan_ids.reverse() # 最新的在前
        
        ids_to_fetch_full = []
        status_updated_count = 0
        
        # --- 第一阶段：增量扫描 & 状态同步 (批量执行) ---
        # 每次取 50 个 ID 进行 Header 和 Flags 扫描
        for chunk in chunk_list(scan_ids, 50):
            id_range = ",".join([id.decode() for id in chunk])
            res, data = mail.fetch(id_range, "(FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT DATE)])")
            
            # 解析返回的数据 (imaplib 返回的是一个列表，偶数项通常是元组数据)
            for i in range(0, len(data), 2):
                if not isinstance(data[i], tuple): continue
                
                header_data = data[i][1]
                meta_str = data[i][0].decode()
                
                # 提取 FLAGS 和 ID
                is_read = parse_flags(meta_str)
                m_id = chunk[i//2].decode() # 对应当前的 ID
                
                # 解析 Header
                headers = email.message_from_bytes(header_data)
                
                # 使用“时间 + 主题”生成唯一的同步 ID
                sync_id = generate_composite_key(headers.get("Subject"), headers.get("Date"))
                
                if db.exists(sync_id):
                    # 已存在，检查并更新已读状态
                    db.update_email_status(sync_id, is_read)
                    status_updated_count += 1
                else:
                    # 调试：输出为什么认为它是新邮件
                    report("debug", f"发现新邮件 ID: [{sync_id}]")
                    ids_to_fetch_full.append((m_id, sync_id, is_read))

        total_to_sync = len(ids_to_fetch_full)
        report("scanned", f"扫描完成。发现 {total_to_sync} 封新邮件，{status_updated_count} 封邮件已更新状态。", 20)
        
        if total_to_sync == 0:
            report("done", "没有发现新邮件。", 100)
            mail.close()
            mail.logout()
            return

        report("fetching", f"正在抓取新邮件内容 (共 {total_to_sync} 封)...", 25)
        
        # --- 第二阶段：正式同步 (批量 Fetch RFC822) ---
        new_count = 0
        start_sync_time = time.time()
        
        for idx_batch, batch in enumerate(chunk_list(ids_to_fetch_full, batch_size), 1):
            batch_uids = ",".join([item[0] for item in batch])
            res, msg_data_list = mail.fetch(batch_uids, "(RFC822)")
            
            # 解析批量返回的内容
            current_batch_count = 0
            for i in range(0, len(msg_data_list), 2):
                if not isinstance(msg_data_list[i], tuple): continue
                
                msg_bytes = msg_data_list[i][1]
                msg = email.message_from_bytes(msg_bytes)
                
                # 匹配对应的元数据 (按顺序匹配)
                # 注意：IMAP fetch 返回的顺序可能与请求顺序一致，也可能按服务器 ID 排序
                # 这里我们通过内容重新校对
                subject = decode_str(msg.get("Subject"))
                sender = decode_str(msg.get("From"))
                date_str = msg.get("Date")
                
                # 重新计算同步 ID 以匹配第一阶段
                sync_id = generate_composite_key(msg.get("Subject"), date_str)
                
                # 查找对应的 is_read (从 batch 中找)
                target_is_read = 0
                for b_item in batch:
                    # b_item[1] 是第一阶段生成的 sync_id
                    if b_item[1] == sync_id:
                        target_is_read = b_item[2]
                        break
                
                body = get_text_from_msg(msg)
                attachments = get_attachments_metadata(msg)
                normalized_dt = normalize_date(date_str)
                
                # --- 新增：自动翻译 ---
                print(f"   📝 正在翻译: {subject[:20]}...")
                body_translation = smart_translate(body)
                
                # --- 新增：AI 智能分析 (摘要、行动项、重要性) ---
                print(f"   🤖 AI 正在分析邮件...")
                # 初始化 AI 分析工具
                ai_skill = EmailSummarySkill() 
                ai_result = ai_skill.analyze_email(body)
                
                email_data = {
                    "message_id": sync_id,
                    "subject": subject,
                    "sender": sender,
                    "date_str": date_str,
                    "normalized_date": normalized_dt,
                    "body": body,
                    "folder": "INBOX",
                    "is_read": target_is_read,
                    "attachments_metadata": json.dumps(attachments, ensure_ascii=False),
                    "body_translation": body_translation,
                    "summary": ai_result.get("summary", ""),
                    "action_items": json.dumps(ai_result.get("action_items", []), ensure_ascii=False),
                    "importance": ai_result.get("importance", "低")
                }
                
                if db.save_email(email_data):
                    new_count += 1
                    current_batch_count += 1
            
            # 打印进度
            processed = min(idx_batch * batch_size, total_to_sync)
            current_progress = 25 + int((processed / total_to_sync) * 70) # 25% - 95%
            
            report("analyzing", f"AI 正在分析邮件 ({processed}/{total_to_sync})...", current_progress, {
                "current": processed,
                "total": total_to_sync,
                "last_subject": subject
            })

        mail.close()
        mail.logout()
        
        report("done", f"同步完成！新增 {new_count} 封邮件。", 100, {"new_count": new_count})

    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    sync_emails(max_scan=500, batch_size=20)
