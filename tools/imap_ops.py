import os
import imaplib
from dotenv import load_dotenv

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def get_mail_connection():
    """获取 IMAP 连接，并针对 163 等邮箱发送 ID 识别信息。"""
    mail = imaplib.IMAP4_SSL("imap.163.com")
    try:
        mail.xatom('ID', '("name" "DeepMailAI" "version" "1.2.0")')
    except Exception as e:
        print(f"⚠️ 发送 ID 握手信息失败: {e}")
    mail.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_AUTH_CODE"))
    return mail


def _set_seen_flag(message_id, add=True):
    """在服务器上设置/取消邮件已读标记。"""
    mail = get_mail_connection()
    try:
        mail.select("INBOX", readonly=False)
        status, data = mail.uid('SEARCH', None, f'(HEADER Message-ID "{message_id}")')
        if status == 'OK' and data[0]:
            uid = data[0].split()[0]
            op = '+FLAGS' if add else '-FLAGS'
            mail.uid('STORE', uid, op, '(\\Seen)')
            action = "已读" if add else "未读"
            print(f"✅ 已在服务器上将邮件标为{action} (UID: {uid.decode()})")
            return True
        print(f"⚠️ 未在服务器上找到对应邮件 (Message-ID: {message_id})")
        return False
    except Exception as e:
        print(f"❌ 状态回写失败: {e}")
        return False
    finally:
        mail.logout()


def mark_as_read_on_server(message_id):
    return _set_seen_flag(message_id, add=True)


def mark_as_unread_on_server(message_id):
    return _set_seen_flag(message_id, add=False)
