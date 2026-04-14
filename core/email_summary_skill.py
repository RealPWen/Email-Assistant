from core.base_skill import BaseSkill

# AI 分析失败时的回退结果
_FALLBACK = {"summary": "", "action_items": [], "importance": "低", "category": "其他", "reason": ""}


class EmailSummarySkill(BaseSkill):
    """邮件智能摘要 / 分类 / 重要性判定技能。"""

    def analyze_email(self, raw_content, custom_instruction="", max_length=6000):
        cleaned = self.clean_html(raw_content)
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length] + "... (内容已截断)"

        system_prompt = self.get_prompt('email_summary', 'email_summary')
        user_prompt = f"{custom_instruction}\n\n待分析邮件正文：\n{cleaned}"

        try:
            print("🌐 正在调用 DeepSeek 官方 API...")
            result = self.call_api(system_prompt, user_prompt)
            return result if result else {**_FALLBACK, "summary": "错误: 未配置 DEEPSEEK_API_KEY", "reason": "缺少 API 密钥"}
        except Exception as e:
            print(f"❌ 官方 API 调用失败: {e}")
            return {**_FALLBACK, "summary": f"分析失败: {e}", "reason": "API 接口异常"}

    def summarize(self, raw_content, custom_instruction=""):
        """向前兼容的汇总方法。"""
        return self.analyze_email(raw_content, custom_instruction).get('summary', '无法生成摘要')
