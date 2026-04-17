"""tools 模块公共工具函数，消除跨文件重复。"""
import os
import sys
import json
import contextlib
import re
import requests
from email.header import decode_header
from email.utils import parsedate_to_datetime
from pathlib import Path
import socket

try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None

# --- Constants & Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
API_PID_FILE = LOGS_DIR / ".api.pid"
SCHEDULER_PID_FILE = LOGS_DIR / ".scheduler.pid"
ENV_FILE = BASE_DIR / ".env"
SYNC_LOCK_FILE = DATA_DIR / ".sync.lock"

# 统一处理 sys.path，确保项目根目录在搜索路径的最前面
# 这对于 Windows 上的多模块导入至关重要
base_dir_str = str(BASE_DIR)
if base_dir_str not in sys.path:
    sys.path.insert(0, base_dir_str)
elif sys.path[1:2] == [base_dir_str]: # Handle edge cases
    pass


_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF"
    "]",
    flags=re.UNICODE,
)


def safe_print(*args, sep=" ", end="\n", file=None, flush=False):
    """安全输出到控制台，避免 Windows GBK 控制台因 emoji 崩溃。"""
    target = file or sys.stdout
    message = sep.join(str(arg) for arg in args)
    try:
        print(message, end=end, file=target, flush=flush)
    except UnicodeEncodeError:
        sanitized = _EMOJI_PATTERN.sub("", message)
        sanitized = sanitized.encode(target.encoding or "utf-8", errors="replace").decode(
            target.encoding or "utf-8",
            errors="replace",
        )
        print(sanitized, end=end, file=target, flush=flush)


def get_local_ip():
    """获取本机在局域网中的 IP 地址，避开虚拟网卡和代理干扰。"""
    try:
        # 建立一个伪连接来探测出站接口 IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        # 使用 114 来探测（避开某些 VPN 拦截的 8.8.8.8）
        s.connect(("114.114.114.114", 80))
        ip = s.getsockname()[0]
        s.close()
        
        # 排除 198.18.x.x (常见于 Clash 等代理软件的虚拟网段)
        if ip.startswith("198.18."):
            import subprocess
            # macOS 尝试直接获取 en0 (WiFi) 的地址
            if sys.platform == "darwin":
                res = subprocess.getoutput("ipconfig getifaddr en0")
                if res and "." in res: return res
            
            # 通用备选方案：尝试获取 hostname 对应的所有 IP
            ips = socket.gethostbyname_ex(socket.gethostname())[2]
            for candidate in ips:
                if not candidate.startswith("127.") and not candidate.startswith("198.18."):
                    return candidate
        return ip
    except Exception:
        return "127.0.0.1"


def decode_str(s):
    """解码邮件头字段（Subject / From 等）。"""
    if not s:
        return ""
    try:
        parts = decode_header(s)
        return "".join(
            p.decode(enc if enc else "utf-8", "ignore") if isinstance(p, bytes) else p
            for p, enc in parts
        )
    except Exception:
        return str(s)


def normalize_date(date_str):
    """将邮件日期转换为标准 ISO 格式。"""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        return None


def generate_composite_key(subject, date_str):
    """根据主题和日期生成稳定的唯一标识码（用于排重）。"""
    norm_date = normalize_date(date_str) or "unknown_date"
    decoded_subject = decode_str(subject)
    norm_subject = " ".join(decoded_subject.split()).strip()
    return f"{norm_date}_{norm_subject}"


def _chunk_text(text, chunk_limit):
    """长文本按段落分块，尽量避免截断语义。"""
    paragraphs = text.split('\n')
    chunks, current = [], ""
    for p in paragraphs:
        if len(p) > chunk_limit:
            if current:
                chunks.append(current.strip())
                current = ""
            for i in range(0, len(p), chunk_limit):
                chunks.append(p[i:i + chunk_limit])
            continue
        if len(current) + len(p) + 1 <= chunk_limit:
            current += p + "\n"
        else:
            chunks.append(current.strip())
            current = p + "\n"
    if current:
        chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk.strip()]


def _translate_with_deepseek(text, target='zh-CN', chunk_limit=3500):
    """使用 DeepSeek 做翻译，适合中国大陆服务器环境。"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY，无法使用 DeepSeek 翻译")

    api_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    target_language = {
        "zh-CN": "简体中文",
        "zh-TW": "繁体中文",
        "en": "English",
        "ja": "日本語",
    }.get(target, target)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    def translate_chunk(chunk):
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是专业邮件翻译助手。请准确翻译用户提供的邮件正文，"
                        f"输出为{target_language}。"
                        "只返回译文，不要加解释、标题、引号或备注。"
                    ),
                },
                {
                    "role": "user",
                    "content": chunk,
                },
            ],
            "stream": False,
        }
        response = requests.post(
            f"{api_base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    if len(text) <= chunk_limit:
        return translate_chunk(text)
    return "\n".join(translate_chunk(chunk) for chunk in _chunk_text(text, chunk_limit))


def _translate_with_google(text, target='zh-CN', chunk_limit=4500):
    """保留 Google 作为可选回退方案。"""
    if GoogleTranslator is None:
        raise RuntimeError("deep-translator 未安装，无法使用 Google 翻译")

    translator = GoogleTranslator(source='auto', target=target)
    if len(text) <= chunk_limit:
        return translator.translate(text)
    return "\n".join(translator.translate(chunk) for chunk in _chunk_text(text, chunk_limit))


def smart_translate(text, target='zh-CN', chunk_limit=4500):
    """智能翻译，默认优先走 DeepSeek，避免中国大陆环境下 Google 不可用。"""
    if not text or not text.strip():
        return ""

    provider = os.getenv("TRANSLATION_PROVIDER", "deepseek").strip().lower()
    providers = {
        "deepseek": ("deepseek",),
        "google": ("google",),
        "auto": ("deepseek", "google"),
    }.get(provider, ("deepseek", "google"))

    last_error = None
    for current in providers:
        try:
            if current == "deepseek":
                return _translate_with_deepseek(text, target=target, chunk_limit=min(chunk_limit, 3500))
            if current == "google":
                return _translate_with_google(text, target=target, chunk_limit=chunk_limit)
        except Exception as e:
            last_error = e
            safe_print(f"⚠️ {current} 翻译失败: {e}")

    safe_print(f"⚠️ 翻译失败: {last_error}")
    return ""


def format_ai_result(ai_res):
    """将 AI 分析结果格式化为数据库可存储的 dict。"""
    return {
        "summary": ai_res.get("summary", ""),
        "action_items": json.dumps(ai_res.get("action_items", []), ensure_ascii=False),
        "importance": ai_res.get("importance", "低"),
        "category": ai_res.get("category", "其他"),
    }


def chunk_list(lst, n):
    """将列表切分为大小为 n 的块。"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def print_header(text, color="blue"):
    """统一的终端标题输出。"""
    colors = {
        "green": "\033[0;32m",
        "blue": "\033[0;34m",
        "yellow": "\033[1;33m",
        "red": "\033[0;31m",
        "nc": "\033[0m"
    }
    c = colors.get(color, colors["nc"])
    nc = colors["nc"]
    safe_print(f"{c}======================================={nc}")
    safe_print(f"{c}    {text}    {nc}")
    safe_print(f"{c}======================================={nc}")


@contextlib.contextmanager
def single_instance_lock(lock_path=SYNC_LOCK_FILE):
    """跨进程互斥锁，避免多个同步任务同时跑导致库里长期堆满占位状态。"""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fh = open(lock_path, "w", encoding="utf-8")
    acquired = False
    try:
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
                acquired = True
            except OSError:
                acquired = False
        else:
            import fcntl
            try:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                acquired = False

        if acquired:
            lock_fh.seek(0)
            lock_fh.truncate()
            lock_fh.write(str(os.getpid()))
            lock_fh.flush()

        yield acquired
    finally:
        if acquired:
            try:
                if os.name == "nt":
                    import msvcrt
                    lock_fh.seek(0)
                    msvcrt.locking(lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        lock_fh.close()
