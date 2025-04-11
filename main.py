import random
import re
import time
from datetime import date
from pathlib import Path
import textwrap
from PIL import ImageDraw, ImageFont
from PIL.Image import new as ImageNew
from astrbot.api.all import *
# 导入签文数据
from data.plugins.astrbot_plugin_sensoji.sensoji_data import sensoji_results

# 定义 JSON 文件路径（存储在插件目录下）
DATA_FILE = Path(__file__).parent / "user_daily_results.json"
CHANGE_COUNT_FILE = Path(__file__).parent / "user_change_counts.json"

# 加载数据
def load_data():
    """从 JSON 文件加载用户抽签结果"""
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# 保存数据
def save_data(data):
    """将用户抽签结果保存到 JSON 文件"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# 加载转运次数数据
def load_change_counts():
    """加载用户转运次数记录"""
    if CHANGE_COUNT_FILE.exists():
        with open(CHANGE_COUNT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# 保存转运次数数据
def save_change_counts(data):
    """保存用户转运次数记录"""
    with open(CHANGE_COUNT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@register("astrbot_plugin_sensoji", "Shouugou", "浅草寺抽签插件", "1.2.5", "repo url")
class SensojiPlugin(Star):

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.enable_change = self.config.get("enable_change_fortune", True)
        self.max_change_times = self.config.get("max_change_fortune_times", 3) if self.enable_change else 0

    async def generate_fortune_image(self, data: dict) -> str:
        """使用 Pillow 生成带样式的运势图片"""
        # 配置参数
        img_width = 1200  # 增加宽度以容纳阴影
        padding = 50
        line_spacing = 1.6  # 增加行间距
        colors = {
            "background": ["#FF9A8B", "#FF6A88", "#FF99AC"],  # 渐变背景
            "title": (211, 47, 47),  # #d32f2f
            "content_bg": (255, 255, 255, 128),  # 半透明白色
            "text": (51, 51, 51),  # #333
            "footer_bg": (255, 255, 255, 178),  # rgba(255,255,255,0.7)
            "footer_text": (102, 102, 102),  # #666
            "shadow": (0, 0, 0, 25)  # 阴影颜色
        }

        # 加载字体（需要实际字体文件支持）
        font_dir = Path(__file__).parent / "fonts"
        title_font = ImageFont.truetype(str(font_dir / "SimHei.ttf"), 48)  # 加大标题字号
        content_font = ImageFont.truetype(str(font_dir / "SimHei.ttf"), 28)
        footer_font = ImageFont.truetype(str(font_dir / "SimHei.ttf"), 24)

        # 预处理文本内容
        def process_text(text: str) -> list:
            """带段落分隔的文本处理"""
            return [para.strip() for para in text.replace('\n\n', '<br>').split('<br>')]

        # 计算区块尺寸
        def text_metrics(text: str, font: ImageFont) -> tuple:
            bbox = font.getbbox(text)
            return (bbox[2] - bbox[0], bbox[3] - bbox[1])

        # 创建渐变背景
        img = ImageNew("RGB", (img_width, 2000), "#FFFFFF")  # 临时高度
        draw = ImageDraw.Draw(img, 'RGBA')

        # 绘制渐变背景
        for i in range(img_width):
            ratio = i / img_width
            r = int(255 * (1 - ratio) + 255 * ratio)
            g = int(154 * (1 - ratio) + 106 * ratio)
            b = int(139 * (1 - ratio) + 136 * ratio)
            draw.line([(i, 0), (i, 2000)], fill=(r, g, b))

        # 绘制标题
        title = "浅草寺抽签"
        title_width, title_height = text_metrics(title, title_font)
        title_x = (img_width - title_width) // 2
        # 标题阴影
        draw.text((title_x + 3, padding + 3), title, font=title_font, fill=colors["shadow"])
        draw.text((title_x, padding), title, font=title_font, fill=colors["title"])

        y_pos = padding + title_height + 40

        # 绘制内容卡片
        card_padding = 30
        content_width = img_width - 2 * card_padding
        content_text = process_text(data.get("message", ""))

        # 计算内容高度
        content_height = 0
        for para in content_text:
            w, h = text_metrics(para, content_font)
            lines = textwrap.wrap(para, width=36)  # 每行18个汉字
            content_height += (len(lines) * h * line_spacing) + 20  # 段落间距

        # 绘制卡片背景
        draw.rounded_rectangle(
            (card_padding, y_pos, img_width - card_padding, y_pos + content_height + 60),
            radius=15,
            fill=colors["content_bg"]
        )

        # 绘制正文内容
        y_pos += 40
        for para in content_text:
            lines = textwrap.wrap(para, width=36)
            for line in lines:
                line_width, line_height = text_metrics(line, content_font)
                draw.text(
                    (card_padding + 40, y_pos),
                    line,
                    font=content_font,
                    fill=colors["text"]
                )
                y_pos += line_height * line_spacing
            y_pos += 20  # 段落后间距

        # 绘制页脚
        if data.get("footer"):
            footer = data["footer"]
            footer_width, footer_height = text_metrics(footer, footer_font)

            # 计算页脚总宽度（包含内边距）
            footer_total_width = footer_width + 40  # 左右各20像素内边距
            footer_start_x = (img_width - footer_total_width) // 2  # 居中计算

            # 绘制背景
            draw.rounded_rectangle(
                (footer_start_x, y_pos + 50,
                 footer_start_x + footer_total_width, y_pos + footer_height + 70),
                radius=8,
                fill=colors["footer_bg"]
            )

            # 绘制文字（在背景内居中）
            text_x = footer_start_x + 20  # 左侧内边距
            text_y = y_pos + 60  # 垂直居中
            draw.text(
                (text_x, text_y),
                footer,
                font=footer_font,
                fill=colors["footer_text"]
            )

        # 裁剪图片到合适高度
        img = img.crop((0, 0, img_width, y_pos + 120))

        # 保存文件
        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(exist_ok=True, parents=True)
        output_path = output_dir / f"{int(time.time())}.png"
        img.save(output_path, quality=95)

        return str(output_path.resolve())

    def remove_escaped_emojis(self,text):
        # 匹配类似 &&confused&& 的转义字符串
        escaped_pattern = re.compile(r"&&\w+&&")
        return escaped_pattern.sub("", text)

    def get_fortune_message(self, selected_result):
        """构建签文结果信息

        Args:
            selected_result (dict): 抽签结果数据.

        Returns:
            str: 构建的签文消息.
        """
        return (
            f"{selected_result['result']}\n\n"
            f"诗文：{selected_result['poetry']}\n\n"
            f"解析：{selected_result['interpretation']}\n\n"
            f"建议：{selected_result['suggestion']}\n\n"
            f"运势细节：{selected_result['horoscope_details']}"
        )

    def get_or_generate_result(self, user_id, today, is_change_fortune=False, result_data=sensoji_results):
        """获取用户的抽签结果或生成新的签文

        Args:
            user_id (str): 用户 ID.
            today (str): 当前日期.
            result_data (list): 用于生成签文的列表数据.
            is_change_fortune (bool): 是否生成转运签.

        Returns:
            str: 返回当前用户的抽签或转运结果.
        """

        user_daily_results = load_data()

        # 检查用户是否已有当天结果
        if user_id in user_daily_results:
            if user_daily_results[user_id]['date'] != today:  # 如果日期过期，清除旧记录
                del user_daily_results[user_id]
                save_data(user_daily_results)

        # 如果用户没有当天的结果，或生成的签为转运签
        if user_id not in user_daily_results or is_change_fortune:
            selected_result = random.choice(result_data)
            result_message = self.get_fortune_message(selected_result)

            user_daily_results[user_id] = {
                'date': today,
                'result': result_message
            }
            save_data(user_daily_results)  # 保存结果

        return user_daily_results[user_id]['result']

    async def _llm_fortune_explanation(self, event: AstrMessageEvent, message: str):
        """使用 LLM 对抽签进行解读"""
        # 定义解签提示模板
        fortune_prompt = (
            f"回复要求：\n"
            f"1. 如果用户尚未抽签，告知用户`需要先抽签，再进行解签`。\n"
            f"2. 如果用户已抽签，则分析签文内容并提供详细解释，包括抽签结果的意义、可能的象征以及建议。\n"
            f"3. 基于解签内容提炼出重点建议，提供一些具体与实际问题相关的指导意见。\n"
            f"4. 保持语气友好、亲切，确保签文解析准确且易于理解，尽量使用简短的一段话结束。\n"
            f"5. 基于角色以合适的语气、称呼等，生成符合人设的回答。\n"
            f"6. 使用纯文本，不要分点，禁用任何Markdown或代码块。\n\n"
            f"内容: {message}"
        )

        # 获取当前对话 ID
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
        context = []

        if curr_cid:
            # 如果当前对话 ID 存在，获取对话对象
            conversation = await self.context.conversation_manager.get_conversation(event.unified_msg_origin, curr_cid)
            if conversation and conversation.history:
                context = json.loads(conversation.history)
        else:
            # 如果当前对话 ID 不存在，创建一个新的对话
            curr_cid = await self.context.conversation_manager.new_conversation(event.unified_msg_origin)
            conversation = await self.context.conversation_manager.get_conversation(event.unified_msg_origin, curr_cid)

        # 调用 LLM 解析签文
        llm_response = await self.context.get_using_provider().text_chat(
            prompt=fortune_prompt,
            contexts=context,
            image_urls=[],
            system_prompt=self.context.provider_manager.selected_default_persona.get("prompt", "")
        )
        # image_url = await self.generate_fortune_image({
        #     "title": "解签结果",
        #     "message": result,
        # })
        image_url = await self.generate_fortune_image({
            "title": "解签结果",
            "message": self.remove_escaped_emojis(llm_response.completion_text).replace("\n", "<br>")
        })
        # url = await self.html_render(TMPL, {"title": "解签结果", "message": self.remove_escaped_emojis(llm_response.completion_text.replace("\n", "<br>"))})
        try:
            yield event.image_result(image_url)
        finally:
            # 发送完成后立即删除
            if os.path.exists(image_url):
                os.remove(image_url)

    @command("抽签帮助")
    async def help(self, event: AstrMessageEvent):
        """显示抽签插件帮助信息"""
        help_msg = """
    浅草寺抽签插件使用说明：

    1. 抽签 - 每日抽取一次签文
    2. 解签 - 解读今日抽到的签文
    {transport_help}
    """.format(
            transport_help="3. 转运 - 重新抽取签文(每日限{}次)".format(
                "∞" if self.max_change_times == 0 else self.max_change_times
            ) if self.enable_change else "3. 转运 - (功能已禁用)"
        )

        yield event.plain_result(help_msg.strip())

    @command("抽签")
    async def select_fortune(self, event: AstrMessageEvent):
        """浅草寺抽签"""
        user_id = event.get_sender_id()
        today = str(date.today())
        result = self.get_or_generate_result(user_id, today)
        image_url = await self.generate_fortune_image({
            "title": "抽签结果",
            "message": result,
        })
        # url = await self.html_render(TMPL, {"title": "抽签结果" ,"message": result.replace("\n", "<br>")})
        try:
            yield event.image_result(image_url)
        finally:
            # 发送完成后立即删除
            if os.path.exists(image_url):
                os.remove(image_url)

    @command("转运")
    async def change_fortune(self, event: AstrMessageEvent):
        """浅草寺转运"""
        if not self.enable_change:
            # url = await self.html_render(TMPL, {
            #     "title": "功能不可用",
            #     "message": "当前管理员已禁用转运功能",
            #     "footer": "如需使用请联系管理员"
            # })
            image_url = await self.generate_fortune_image({
                "title": "功能不可用",
                "message": "当前管理员已禁用转运功能",
                "footer": "如需使用请联系管理员"
            })
            try:
                yield event.image_result(image_url)
            finally:
                # 发送完成后立即删除
                if os.path.exists(image_url):
                    os.remove(image_url)
            return

        user_id = event.get_sender_id()
        today = str(date.today())
        user_daily_results = load_data()
        change_counts = load_change_counts()

        # 初始化用户转运次数记录
        if user_id not in change_counts:
            change_counts[user_id] = {"date": today, "count": 0}

        # 检查是否是新的一天
        if change_counts[user_id]["date"] != today:
            change_counts[user_id] = {"date": today, "count": 0}

        # 检查转运次数限制
        if self.max_change_times > 0 and change_counts[user_id]["count"] >= self.max_change_times:
            # url = await self.html_render(TMPL, {
            #     "title": "转运失败",
            #     "message": f"今日转运次数已达上限（{self.max_change_times}次）"
            # })
            image_url = await self.generate_fortune_image({
                "title": "转运失败",
                "message": f"今日转运次数已达上限（{self.max_change_times}次）"
            })
            try:
                yield event.image_result(image_url)
            finally:
                # 发送完成后立即删除
                if os.path.exists(image_url):
                    os.remove(image_url)
            return

        # 检查用户是否已有抽签结果；无则抽签，有则重新抽取转运签
        is_change_fortune = user_id in user_daily_results and user_daily_results[user_id]['date'] == today
        result = self.get_or_generate_result(user_id, today, is_change_fortune)

        # 增加转运次数计数
        if is_change_fortune:
            change_counts[user_id]["count"] += 1
            save_change_counts(change_counts)

        # url = await self.html_render(TMPL, {
        #     "title": "转运结果",
        #     "message": result.replace("\n", "<br>"),
        #     "footer": f"今日已转运 {change_counts[user_id]['count']}/{self.max_change_times if self.max_change_times > 0 else '∞'} 次"
        # })
        image_url = await self.generate_fortune_image({
            "title": "转运结果",
            "message": result.replace("\n", "<br>"),
            "footer": f"今日已转运 {change_counts[user_id]['count']}/{self.max_change_times if self.max_change_times > 0 else '∞'} 次"
        })
        try:
            yield event.image_result(image_url)
        finally:
            # 发送完成后立即删除
            if os.path.exists(image_url):
                os.remove(image_url)

    @command("解签")
    async def explain_fortune(self, event: AstrMessageEvent):
        """LLM 解签"""
        user_id = event.get_sender_id()
        today = str(date.today())
        user_daily_results = load_data()

        message = (
            self.get_or_generate_result(user_id, today)
            if user_id in user_daily_results and user_daily_results[user_id]['date'] == today
            else "今日尚未抽签"
        )
        async for resp in self._llm_fortune_explanation(event, message):
            yield resp

    @llm_tool("explain_fortune")
    async def explain_fortune_tool(self, event: AstrMessageEvent):
        """Explain the result of a fortune from Sensoji Temple.应当在`解签``解释一下抽的签`时被调用。"""
        user_id = event.get_sender_id()
        today = str(date.today())
        user_daily_results = load_data()

        message = (
            self.get_or_generate_result(user_id, today)
            if user_id in user_daily_results and user_daily_results[user_id]['date'] == today
            else "今日尚未抽签"
        )
        async for resp in self._llm_fortune_explanation(event, message):
            yield resp

