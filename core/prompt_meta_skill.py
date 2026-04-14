import json
from core.base_skill import BaseSkill


class PromptMetaSkill(BaseSkill):
    """通过 AI 优化和改写 System Prompt 的元技能（Prompt 硬编码，防止被用户误改）。"""

    def __init__(self):
        super().__init__()
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

    def _build_user_content(self, current_prompt, user_request):
        return (
            f"【原始 Prompt】:\n{current_prompt}\n\n"
            f"【用户的修改要求】:\n{user_request}\n\n"
            "请直接输出修改后的完整 Prompt 内容："
        )

    def optimize_prompt(self, current_prompt, user_request):
        """同步调用 AI 改写 Prompt。"""
        if not self.api_key:
            return "错误：未配置 DEEPSEEK_API_KEY，无法使用 Prompt 实验室。"
        try:
            result = self.call_api(
                self.meta_prompt,
                self._build_user_content(current_prompt, user_request),
                json_mode=False
            )
            if result is None:
                return "错误：未配置 DEEPSEEK_API_KEY"
            # 清理可能的 markdown 标记
            import re
            result = re.sub(r'^```\w*\n?', '', result)
            result = re.sub(r'\n?```$', '', result)
            return result.strip()
        except Exception as e:
            return f"❌ 优化指令失败: {e}"

    def optimize_prompt_stream(self, current_prompt, user_request):
        """流式调用 AI 改写 Prompt，逐字返回。"""
        if not self.api_key:
            yield "错误：未配置 DEEPSEEK_API_KEY，无法使用 Prompt 实验室。"
            return
        try:
            response = self.call_api(
                self.meta_prompt,
                self._build_user_content(current_prompt, user_request),
                json_mode=False, stream=True
            )
            if response is None:
                yield "错误：未配置 DEEPSEEK_API_KEY"
                return
            with response:
                for line in response.iter_lines():
                    if not line:
                        continue
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
            yield f"\n❌ 流式优化指令失败: {e}"
