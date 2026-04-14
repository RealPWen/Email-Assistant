import os
from bs4 import BeautifulSoup
import requests
import json
import re
from datetime import datetime
from dotenv import load_dotenv

class TodoSkill:
    """
    专门用于从邮件正文中提取待办事项详情的 AI 技能。
    识别截止日期、优先级、具体行动方案及完成标准。
    """
    
    def __init__(self):
        # 加载环境变量
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(base_dir, ".env"))
        
        # 官方 API 配置
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.api_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.api_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    def clean_html(self, html_content):
        """清洗 HTML"""
        if not html_content: return ""
        soup = BeautifulSoup(html_content, 'html.parser')
        for element in soup(['style', 'script', 'head', 'meta', 'link']):
            element.decompose()
        return soup.get_text(separator=' ').strip()

    def extract_todo_info(self, raw_content, current_time=None):
        """调用 AI 提取待办信息"""
        if not self.api_key:
            return {"error": "API Key not configured"}

        cleaned_text = self.clean_html(raw_content)
        if len(cleaned_text) > 5000:
            cleaned_text = cleaned_text[:5000]

        if not current_time:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        from core.db_manager import DBManager
        db = DBManager()
        system_prompt_template = db.get_prompt('todo_extract')
        
        if not system_prompt_template: # Fallback just in case DB doesn't have it
            from core.default_prompts import DEFAULT_PROMPTS
            system_prompt_template = DEFAULT_PROMPTS['todo_extract']
            
        system_prompt = system_prompt_template.replace("{current_time}", current_time)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.api_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"邮件内容如下：\n{cleaned_text}"}
            ],
            "response_format": {"type": "json_object"}
        }

        try:
            response = requests.post(f"{self.api_base_url}/chat/completions", json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            res_data = response.json()
            return json.loads(res_data['choices'][0]['message']['content'])
        except Exception as e:
            print(f"❌ Todo 提取失败: {e}")
            return {
                "title": "提起失败",
                "due_date": datetime.now().strftime("%Y-%m-%d"),
                "priority": "Normal",
                "content": f"错误详情: {str(e)}",
                "details": "请手动输入。"
            }
