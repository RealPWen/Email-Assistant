import os
import json
import requests
from dotenv import load_dotenv

class PromptMetaSkill:
    """
    专门用于通过 AI 优化和改写 System Prompt 的元技能。
    此技能的 Prompt 是硬编码的，防止被用户不小心改坏。
    """
    
    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(base_dir, ".env"))
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.api_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.api_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        
        # 冻结的 Meta-Prompt
        self.meta_prompt = (
            "你是一个顶尖的 Prompt Engineer (提示词工程师)。"
            "用户不仅依赖这段指令来提取数据，还依赖它输出特定的 JSON 格式。如果格式要求被破坏，整个系统将崩溃。"
            "你的任务是：基于用户提供的新需求，对传入的旧提示词（System Prompt）进行**局部修改和优化**。\n\n"
            "【强制规则】：\n"
            "1. 必须完全保留原有的 JSON 数据结构要求（例如 `{ \"summary\": \"...\", ... }`），绝不能删除字段要求。\n"
            "2. 你的输出内容将直接保存进数据库，作为机器运行的系统指令。\n"
            "3. 绝对不要输出任何 markdown 代码块（不要用 ``` 包含），不要输出任何寒暄、警告或解释说明！只输出纯文本的新 Prompt 文字本身！\n"
            "4. 如果你觉得用户的要求会导致 JSON 崩溃，请在原提示词末尾谨慎添加新规则，而不是大改。"
        )

    def optimize_prompt(self, current_prompt, user_request):
        """调用 AI 改写 Prompt"""
        if not self.api_key:
            return "错误：未配置 DEEPSEEK_API_KEY，无法使用 Prompt 实验室。"
            
        user_content = (
            f"【原始 Prompt】:\n{current_prompt}\n\n"
            f"【用户的修改要求】:\n{user_request}\n\n"
            "请直接输出修改后的完整 Prompt 内容："
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.api_model,
            "messages": [
                {"role": "system", "content": self.meta_prompt},
                {"role": "user", "content": user_content}
            ],
            "stream": False
        }
        
        try:
            response = requests.post(f"{self.api_base_url}/chat/completions", json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            res_data = response.json()
            new_prompt = res_data['choices'][0]['message']['content'].strip()
            
            # 清理可能的 markdown 标记
            if new_prompt.startswith("```"):
                new_prompt = new_prompt.split("\n", 1)[-1]
            if new_prompt.endswith("```"):
                new_prompt = new_prompt.rsplit("\n", 1)[0]
                
            return new_prompt.strip()
        except Exception as e:
            return f"❌ 优化指令失败: {str(e)}"

    def optimize_prompt_stream(self, current_prompt, user_request):
        """流式调用 AI 改写 Prompt，逐字返回"""
        if not self.api_key:
            yield "错误：未配置 DEEPSEEK_API_KEY，无法使用 Prompt 实验室。"
            return
            
        user_content = (
            f"【原始 Prompt】:\n{current_prompt}\n\n"
            f"【用户的修改要求】:\n{user_request}\n\n"
            "请直接输出修改后的完整 Prompt 内容："
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.api_model,
            "messages": [
                {"role": "system", "content": self.meta_prompt},
                {"role": "user", "content": user_content}
            ],
            "stream": True # 开启流式输出
        }
        
        try:
            with requests.post(f"{self.api_base_url}/chat/completions", json=payload, headers=headers, stream=True, timeout=60) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            data_str = line_str[6:]
                            if data_str == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data_str)
                                content = chunk['choices'][0]['delta'].get('content', '')
                                if content:
                                    yield content
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            yield f"\n❌ 流式优化指令失败: {str(e)}"
