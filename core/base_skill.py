import os
import re
import json
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# 项目根目录 & 环境变量（只加载一次）
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class BaseSkill:
    """所有 AI 技能的基类，封装公共初始化和 API 调用逻辑。"""

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.api_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.api_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self._db = None

    @property
    def db(self):
        if self._db is None:
            from core.db_manager import DBManager
            self._db = DBManager()
        return self._db

    def clean_html(self, html_content):
        """深度清洗 HTML，移除样式表、脚本、元数据等噪音。"""
        if not html_content:
            return ""
        html_content = re.sub(r'<!--\[if.*?<!\[endif\]-->', '', html_content, flags=re.DOTALL)
        soup = BeautifulSoup(html_content, 'html.parser')
        for element in soup(['style', 'script', 'head', 'meta', 'link', 'title', 'svg', 'img']):
            element.decompose()
        for br in soup.find_all('br'):
            br.replace_with('\n')
        for div in soup.find_all(['div', 'p', 'tr']):
            div.append('\n')
        text = soup.get_text(separator=' ')
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        return text.strip()

    def call_api(self, system_prompt, user_prompt, json_mode=True, stream=False):
        """调用 DeepSeek API（兼容 OpenAI 格式）。"""
        if not self.api_key:
            return None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.api_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": stream,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        response = requests.post(
            f"{self.api_base_url}/chat/completions",
            json=payload, headers=headers,
            timeout=60, stream=stream
        )
        response.raise_for_status()

        if stream:
            return response

        data = response.json()
        content = data['choices'][0]['message']['content']
        return json.loads(content) if json_mode else content.strip()

    def get_prompt(self, skill_name, fallback_key=None):
        """从 DB 获取 prompt，失败时回退到默认值。"""
        prompt = self.db.get_prompt(skill_name)
        if not prompt and fallback_key:
            from core.default_prompts import DEFAULT_PROMPTS
            prompt = DEFAULT_PROMPTS.get(fallback_key, "")
        return prompt
