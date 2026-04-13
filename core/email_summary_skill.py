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
        
        system_prompt = (
            "你是一个专业的邮件智能助理。请分析以下邮件内容，并严格以 JSON 格式返回结果。\n"
            "【强制语言要求】：无论原始邮件使用何种语言，JSON 中的所有文本字段必须使用【简体中文】。 \n\n"
            "【当前用户画像】：\n"
            "- 用户姓名：潘闻 (PAN WEN)\n"
            "- 身份：香港大学 (HKU) 研究生\n"
            "- 专业：数据科学 (Data Science)\n"
            "- 核心目标：自我提升、学业精进、拓宽行业及学术视野。\n\n"
            "JSON 结构要求：\n"
            "{\n"
            "  \"summary\": \"一句话总结邮件核心内容\",\n"
            "  \"action_items\": [\"行动项1\", \"行动项2\"], \n"
            "  \"importance\": \"高/低\",\n"
            "  \"category\": \"课程内容/学术研究/讲座与学术/财务/职业发展/校内事务/系统通知/社交与活动/校企与外部/推广/其他\",\n"
            "  \"reason\": \"判定重要性和分类的原因\"\n"
            "}\n\n"
            "【分类判定标准】：\n"
            "1. 课程内容 (Course)：包含课程编号（如 COMP, DASC, MATH）、Moodle 提醒、作业、考试、成绩发布等。\n"
            "2. 学术研究 (Research)：研究参与者招募、实验室通知、项目调研。 \n"
            "3. 讲座与学术 (Seminar)：研讨会、讲座预约、学术期刊、图书馆资源、实验室新闻。\n"
            "4. 财务 (Financial)：学费、缴费单、银行转账、薪资单、消费凭证、数字货币结单、金融指标报告 (如 VIX/SKEW)。\n"
            "5. 职业发展 (Career)：实习、校招、职业辅导 (CEDARS Career)、面试邀请、招聘讲座。\n"
            "6. 校内事务 (Campus)：学生处 (CEDARS) 综合通知、校内设施调整、校园新闻、通识教育通知。\n"
            "7. 系统通知 (Notification) ：验证码、重置密码、系统维护、服务安全提醒。\n"
            "8. 社交与活动 (Social)：社团活动、聚会邀请、校友会快讯、学生会选举。\n"
            "9. 校企与外部 (External)：合作伙伴通知、外部机构函件、校外活动推荐。\n"
            "10. 推广 (Promotion)：不相关的商业广告、APP 推广、非学术 Newsletter。\n"
            "11. 其他 (Other)：不属于以上任何类别的邮件。\n\n"
            "【重要性判定标准】：\n"
            "1. 重要 (高)：需满足以下任一条件：\n"
            "   - 有明确截止日期 (Deadline)、成绩发布、账户安全安全警报。\n"
            "   - 财务相关：银行结单 (Statement)、薪资单、缴费通知。\n"
            "   - 【个性化高价值】：与数据科学 (Data Science) 学习/职业/研究直接相关的资讯；香港大学 (HKU) 的校务/奖学金/选课重要通知；能够显著拓宽视野、对个人成长有益的讲座、研讨会或高质量学术快讯。\n"
            "2. 不重要 (低)：常规新闻速报、没有任何截止日期的普通社团简报、已失效的信息、纯商业推广广告、系统自动回复的 Acknowledgement。\n\n"
            "【特别警告】：完全忽略 HTML 噪音。严禁输出任何非 JSON 的解释性文字。"
        )
        
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
