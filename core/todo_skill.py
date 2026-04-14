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

        system_prompt = f"""你是一个高效的任务管理专家。请从提供的邮件内容中提取待办事项详情。
【当前时间参考】：{current_time}

请严格以 JSON 格式返回以下字段（使用简体中文）：
{{
  "title": "任务简洁标题",
  "due_date": "识别到的截止日期，格式必须为 YYYY-MM-DD。若文中提到'明天'或'下周五'，请根据参考时间计算出具体日期。若无日期，请分析内容给出最合理的预估日期。",
  "priority": "High / Normal / Low (根据重要性和紧急程度判定)",
  "content": "具体要做什么的一句话摘要",
  "details": "具体的执行步骤及'怎么样才算完成'的判断标准。"
}}

【提取规则】：
- 如果是作业/考试，优先级设为 High。
- 如果是报名/截止日期，due_date 为该日期前一天或当天。
- 忽略广告和推广信息。如果没有发现实质性待办，请在 title 中说明'未发现明确待办'。 
严禁输出任何非 JSON 的解释性文字。"""

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
