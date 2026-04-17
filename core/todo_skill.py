from datetime import datetime
from core.base_skill import BaseSkill
from tools.utils import safe_print


class TodoSkill(BaseSkill):
    """从邮件正文中提取待办事项详情的 AI 技能。"""

    def extract_todo_info(self, raw_content, current_time=None):
        if not self.api_key:
            return {"error": "API Key not configured"}

        cleaned = self.clean_html(raw_content)
        if len(cleaned) > 5000:
            cleaned = cleaned[:5000]

        current_time = current_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        template = self.get_prompt('todo_extract', 'todo_extract')
        system_prompt = template.replace("{current_time}", current_time)

        try:
            result = self.call_api(system_prompt, f"邮件内容如下：\n{cleaned}")
            return result if result else {"error": "API Key not configured"}
        except Exception as e:
            safe_print(f"❌ Todo 提取失败: {e}")
            return {
                "title": "提取失败",
                "due_date": datetime.now().strftime("%Y-%m-%d"),
                "priority": "Normal",
                "content": f"错误详情: {e}",
                "details": "请手动输入。"
            }
