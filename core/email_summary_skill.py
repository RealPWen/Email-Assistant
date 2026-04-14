import os
from bs4 import BeautifulSoup
import requests
import json
import re
from dotenv import load_dotenv

class EmailSummarySkill:
    """
    专门用于邮件汇总的技能接口。
    系统目前已完全切换为 DeepSeek 官方 API 运行。
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
        """
        深度清洗 HTML，移除样式表、脚本、元数据等噪音。
        """
        if not html_content:
            return ""
            
        # 移除常见的嵌入式注释和乱码 (如 [if mso])
        html_content = re.sub(r'<!--\[if.*?<!\[endif\]-->', '', html_content, flags=re.DOTALL)
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 移除干扰标签
        for element in soup(['style', 'script', 'head', 'meta', 'link', 'title', 'svg', 'img']):
            element.decompose()
            
        # 尝试保留基本结构（换行）
        for br in soup.find_all('br'):
            br.replace_with('\n')
        for div in soup.find_all(['div', 'p', 'tr']):
            div.append('\n')
            
        text = soup.get_text(separator=' ')
        
        # 清洗空白字符
        text = re.sub(r'\n\s*\n', '\n\n', text) # 压缩多余空行
        text = re.sub(r' +', ' ', text)         # 压缩多余空格
        
        return text.strip()

    def analyze_with_official_api(self, system_prompt, user_prompt):
        """
        调用 DeepSeek 官方 API (OpenAI 兼容格式)
        """
        if not self.api_key:
            return {
                "summary": "错误: 未配置 DEEPSEEK_API_KEY",
                "action_items": [],
                "importance": "低",
                "category": "其他",
                "reason": "缺少 API 密钥"
            }
            
        print("🌐 正在调用 DeepSeek 官方 API...")
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
            "response_format": {"type": "json_object"},
            "stream": False
        }
        
        try:
            response = requests.post(f"{self.api_base_url}/chat/completions", json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            res_data = response.json()
            content = res_data['choices'][0]['message']['content']
            return json.loads(content)
        except Exception as e:
            print(f"❌ 官方 API 调用失败: {e}")
            return {
                "summary": f"分析失败: {str(e)}",
                "action_items": [],
                "importance": "低",
                "category": "其他",
                "reason": "API 接口异常"
            }

    def analyze_email(self, raw_content, custom_instruction="", max_length=6000):
        """
        核心分析方法：直接使用 DeepSeek 官方 API。
        """
        cleaned_text = self.clean_html(raw_content)
        
        # 长度截断
        if len(cleaned_text) > max_length:
            cleaned_text = cleaned_text[:max_length] + "... (内容已截断)"
        
        from core.db_manager import DBManager
        db = DBManager()
        system_prompt = db.get_prompt('email_summary')
        
        if not system_prompt: # Fallback just in case DB doesn't have it
            from core.default_prompts import DEFAULT_PROMPTS
            system_prompt = DEFAULT_PROMPTS['email_summary']
        
        user_prompt = f"{custom_instruction}\n\n待分析邮件正文：\n{cleaned_text}"
        
        # 直接调用官方 API
        return self.analyze_with_official_api(system_prompt, user_prompt)

    def summarize(self, raw_content, custom_instruction=""):
        """
        向前兼容的汇总方法。
        """
        res = self.analyze_email(raw_content, custom_instruction)
        return res.get('summary', '无法生成摘要')

if __name__ == "__main__":
    # 冒烟测试
    skill = EmailSummarySkill()
    print("--- 技能初始化成功 (仅限 API) ---")
    print(f"API 模型: {skill.api_model}")
