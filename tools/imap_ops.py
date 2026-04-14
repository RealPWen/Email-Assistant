import os
import imaplib
from dotenv import load_dotenv

# 加载配置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

def get_mail_connection():
    """获取 IMAP 连接，并针对 163 等邮箱发送 ID 识别信息"""
    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_AUTH_CODE")
    imap_server = "imap.163.com"
    
    mail = imaplib.IMAP4_SSL(imap_server)
    
    # 【核心修复】：对于 163 等邮箱，开启 IMAP 后验证新设备必须先发送 ID 信息
    # 否则即使授权码正确，服务器也会返回 "LOGIN Login error or password error"
    try:
        mail.xatom('ID', '("name" "DeepMailAI" "version" "1.2.0")')
    except Exception as e:
        print(f"⚠️ 发送 ID 握手信息失败（可能非 163 邮箱）: {e}")
        
    mail.login(email_user, email_pass)
    return mail

def mark_as_read_on_server(message_id):
    """
    通过 Message-ID 在服务器上将邮件标为已读。
    """
    mail = get_mail_connection()
    try:
        mail.select("INBOX", readonly=False)
        
        # 通过 Message-ID 搜索 UID
        # 注意：Message-ID 需要保留尖括号，如 <abc@def.com>
        # 如果数据库存的是没带尖括号的，这里搜索可能由于 163 服务器要求精准匹配而失败
        search_query = f'(HEADER Message-ID "{message_id}")'
        status, data = mail.uid('SEARCH', None, search_query)
        
        if status == 'OK' and data[0]:
            uid = data[0].split()[0]
            # 执行标记
            mail.uid('STORE', uid, '+FLAGS', '(\\Seen)')
            print(f"✅ 已在服务器上将邮件标为已读 (UID: {uid.decode()})")
            return True
        else:
            print(f"⚠️ 未在服务器上找到对应的邮件 (Message-ID: {message_id})")
            return False
    except Exception as e:
        print(f"❌ 状态回写失败: {e}")
        return False
    finally:
        mail.logout()

def mark_as_unread_on_server(message_id):
    """
    通过 Message-ID 在服务器上将邮件标为未读。
    """
    mail = get_mail_connection()
    try:
        mail.select("INBOX", readonly=False)
        search_query = f'(HEADER Message-ID "{message_id}")'
        status, data = mail.uid('SEARCH', None, search_query)
        
        if status == 'OK' and data[0]:
            uid = data[0].split()[0]
            mail.uid('STORE', uid, '-FLAGS', '(\\Seen)')
            print(f"✅ 已在服务器上将邮件标为未读 (UID: {uid.decode()})")
            return True
        else:
            print(f"⚠️ 未发现邮件: {message_id}")
            return False
    except Exception as e:
        print(f"❌ 状态回写失败: {e}")
        return False
    finally:
        mail.logout()

if __name__ == "__main__":
    # 测试代码 (需替换为真实的 Message-ID)
    # test_id = "<your-message-id-here>"
    # mark_as_read_on_server(test_id)
    pass
