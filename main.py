import random
import re
import time
from datetime import date
from pathlib import Path
from PIL import ImageDraw, ImageFont
from PIL.Image import new as ImageNew
from astrbot.api.all import *
from asyncio import create_task, sleep
from datetime import datetime, timedelta
# 导入签文数据
from data.plugins.astrbot_plugin_sensoji_pro.sensoji_data import sensoji_results

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

@register("astrbot_plugin_sensoji_pro", "xiamuceer-j", "浅草寺抽签插件-PRO", "1.2.0", "https://github.com/xiamuceer-j/astrbot_plugin_sensoji_pro")
class SensojiPlugin(Star):

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.enable_change = self.config.get("enable_change_fortune", True)
        self.max_change_times = self.config.get("max_change_fortune_times", 3) if self.enable_change else 0
        self.daily_cleanup = self.config.get("daily_cleanup", 1)
        create_task(self.daily_cleanup_task())

    async def daily_cleanup_task(self):
        if self.daily_cleanup <= 0:
            logger.info(f"每日清理功能已关闭（daily_cleanup={self.daily_cleanup}）")
            return

        while True:
            now = datetime.now()
            next_run = (now + timedelta(days=self.daily_cleanup)).replace(hour=0, minute=0, second=0, microsecond=0)
            sleep_seconds = (next_run - now).total_seconds()

            hours = int(sleep_seconds // 3600)
            minutes = int((sleep_seconds % 3600) // 60)
            seconds = int(sleep_seconds % 60)
            logger.info(f"[{now}] 距下次清理还有 {hours} 小时 {minutes} 分钟 {seconds} 秒...")

            await sleep(sleep_seconds)

            output_dir = Path(__file__).parent / "output"
            if output_dir.exists():
                for file in output_dir.glob("*.png"):
                    try:
                        file.unlink()
                        logger.info(f"已删除文件：{file}")
                    except Exception as e:
                        logger.warning(f"无法删除文件 {file}: {e}")

    async def generate_fortune_image(self, data: dict) -> str:
        """优化版签文生成（智能分段+混合布局）"""
        # 配置参数
        img_width = 800
        padding = 60
        colors = {
            "background": "#FFF5E6",
            "title": (188, 42, 26),
            "text": (51, 51, 51),
            "border": (205, 128, 83),
            "stamp": (227, 66, 52)
        }

        # 加载字体
        font_dir = Path(__file__).parent / "fonts"
        title_font = ImageFont.truetype(str(font_dir / "FZSTK.ttf"), 84)
        sx_content_font = ImageFont.truetype(str(font_dir / "SSQFT.ttf"), 66)
        s_content_font = ImageFont.truetype(str(font_dir / "SYST.otf"), 42)
        h_content_font = ImageFont.truetype(str(font_dir / "BGTXT.ttf"), 38)
        stamp_font = ImageFont.truetype(str(font_dir / "STLITI.ttf"), 46)

        def smart_segment(text: str) -> list:
            """智能分段逻辑优化"""
            markers = ["解析：", "建议：", "运势细节："]
            segments = []
            buffer = ""
            for line in text.split('\n'):
                line = line.strip()
                if any(line.startswith(m) for m in markers):
                    if buffer:
                        segments.append(buffer)
                        buffer = ""
                    segments.append("◆" + line)
                else:
                    buffer += line + " "
            if buffer:
                segments.append(buffer)
            return segments

        def calculate_layout(segments: list) -> tuple:
            """混合布局计算（竖排+横排）"""
            layout_data = []
            total_height = padding + 120
            right_margin = 80
            left_margin = 80
            first_vertical = True

            for seg in segments:
                if not seg.strip():
                    continue

                seg = seg.replace('\u200b', '').replace('\ufeff', '')

                is_horizontal = any(seg.startswith(f"◆{m}") for m in ["解析：", "建议：", "运势细节："])

                if is_horizontal:
                    # seg = seg.lstrip("◆")
                    available_width = img_width - right_margin - left_margin

                    lines = []
                    current_line = []
                    current_width = 0
                    for char in seg:
                        bbox = h_content_font.getbbox(char)
                        char_width = bbox[2] - bbox[0]
                        if current_width + char_width > available_width:
                            lines.append("".join(current_line))
                            current_line = [char]
                            current_width = char_width
                        else:
                            current_line.append(char)
                            current_width += char_width
                    if current_line:
                        lines.append("".join(current_line))

                    line_height = 45
                    seg_height = len(lines) * line_height + 50

                    layout_data.append({
                        "type": "horizontal",
                        "content": lines,
                        "height": seg_height,
                        "line_height": line_height
                    })
                    total_height += seg_height
                else:
                    if first_vertical and "　" in seg and " 诗文：" in seg and "；" in seg:
                        first_vertical = False
                        parts = seg.split(" 诗文：", 1)
                        fortune_info = parts[0]
                        poem_parts = parts[1].split("；", 1)
                        if len(poem_parts) == 2:
                            line1 = poem_parts[0] + '；'
                            line2 = poem_parts[1]

                            col1 = [char for char in fortune_info]
                            col2 = [char for char in "诗文："]
                            col3 = [char for char in line1]
                            col4 = [char for char in line2]

                            max_len = max(len(col1), len(col2), len(col3), len(col4))
                            seg_height = max_len * 45 + 40  # Using line_height and section_spacing

                            layout_data.append({
                                "type": "vertical",
                                "columns": [col1, col3, col4],
                                "height": seg_height,
                                "col_width": 60,  # Adjust as needed
                                "line_height": 45
                            })
                            total_height += seg_height
                            continue  # Skip the old vertical logic
                    else:
                        # 默认采用横排格式
                        available_width = img_width - right_margin - left_margin

                        lines = []
                        current_line = []
                        current_width = 0
                        for char in seg:
                            bbox = h_content_font.getbbox(char)
                            char_width = bbox[2] - bbox[0]
                            if current_width + char_width > available_width:
                                lines.append("".join(current_line))
                                current_line = [char]
                                current_width = char_width
                            else:
                                current_line.append(char)
                                current_width += char_width
                        if current_line:
                            lines.append("".join(current_line))

                        line_height = 45
                        seg_height = len(lines) * line_height + 50

                        layout_data.append({
                            "type": "horizontal",
                            "content": lines,
                            "height": seg_height,
                            "line_height": line_height
                        })
                        total_height += seg_height

            return layout_data, total_height + 300, right_margin

        # 创建画布
        segments = smart_segment(data.get("message"))
        layout_data, total_height, right_margin = calculate_layout(segments)

        img = ImageNew("RGB", (img_width, total_height), colors["background"])
        draw = ImageDraw.Draw(img)

        # 绘制背景纹理
        for i in range(0, img_width, 6):
            draw.line([(i, 0), (i, total_height)], fill=(230, 220, 210), width=1)

        # 绘制边框
        border_width = 10
        draw.rectangle(
            [border_width, border_width, img_width - border_width, total_height - border_width],
            outline=colors["border"],
            width=2
        )

        # 绘制标题
        title = data.get("title")
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_x = (img_width - title_bbox[2]) // 2
        draw.text((title_x, padding + 20), title, fill=colors["title"], font=title_font)

        # 混合排版逻辑
        y_pos = padding + title_bbox[3] + 140
        left_margin = 80

        for seg_data in layout_data:
            if seg_data["type"] == "horizontal":
                y_pos += 30
                for line in seg_data["content"]:
                    draw.text((left_margin, y_pos), line, fill=colors["text"], font=h_content_font)
                    y_pos += seg_data["line_height"]
                y_pos += 50
            elif seg_data["type"] == "vertical":
                columns = seg_data["columns"]
                col_width = seg_data["col_width"]
                line_height = seg_data["line_height"]
                spacing = 150  # 增加竖排的列间距
                start_x = left_margin + 80
                max_y = y_pos

                for col_idx, column in enumerate(columns):
                    current_y = y_pos
                    if col_idx == 0:
                        for char in column:
                            draw.text(
                                (start_x + col_idx * col_width + col_idx * spacing, current_y),
                                char,
                                fill=colors["text"],
                                font=sx_content_font
                            )
                            current_y += line_height * 1.6
                    else:
                        for char in column:
                            draw.text(
                                (start_x + col_idx * col_width + col_idx * spacing, current_y),
                                char,
                                fill=colors["text"],
                                font=s_content_font
                            )
                            current_y += line_height
                    max_y = max(max_y, current_y)
                y_pos = max_y

        # 印章绘制优化 - 调整位置以重合
        stamp_text = "浅草寺"
        stamp_bbox = draw.textbbox((0, 0), stamp_text, font=stamp_font)
        stamp_size = max(stamp_bbox[2] - stamp_bbox[0], 50)

        # 计算印章可以出现的右下角区域
        right_margin_buffer = 20  # 留出一些右边距
        bottom_margin_buffer = 20  # 留出一些底部边距

        min_stamp_x = int(img_width * 0.6)
        max_stamp_x = img_width - stamp_size - right_margin_buffer

        min_stamp_y = int(total_height * 0.8)
        max_stamp_y = total_height - stamp_size - bottom_margin_buffer

        # 确保 min_stamp_x 不大于 max_stamp_x
        if min_stamp_x > max_stamp_x:
            min_stamp_x = max_stamp_x  # 或者你可以根据需要设置一个默认值

        # 确保 min_stamp_y 不大于 max_stamp_y
        if min_stamp_y > max_stamp_y:
            min_stamp_y = max_stamp_y  # 或者你可以根据需要设置一个默认值

        # 生成随机的 x 和 y 坐标
        stamp_x = random.randint(min_stamp_x, max_stamp_x)
        stamp_y = random.randint(min_stamp_y, max_stamp_y)

        draw.ellipse(
            [stamp_x, stamp_y, stamp_x + stamp_size, stamp_y + stamp_size],
            outline=colors["stamp"],
            width=2
        )
        # 调整文字位置，使其居中于随机生成的圆内
        text_x = stamp_x + (stamp_size - stamp_bbox[2]) // 2
        text_y = stamp_y + (stamp_size - stamp_bbox[3]) // 2 - (stamp_bbox[1])  # 稍微调整文字的垂直位置
        draw.text(
            (text_x, text_y),
            stamp_text,
            fill=colors["stamp"],
            font=stamp_font
        )

        # 最终裁剪
        img = img.crop((0, 0, img_width, total_height))

        # 保存文件
        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"sign_{int(time.time())}.png"
        img.save(output_path, quality=95, optimize=True)

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
            "message": self.remove_escaped_emojis(llm_response.completion_text)
        })
        # url = await self.html_render(TMPL, {"title": "解签结果", "message": self.remove_escaped_emojis(llm_response.completion_text.replace("\n", "<br>"))})
        yield event.image_result(image_url)

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
        yield event.image_result(image_url)

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
            yield event.image_result(image_url)
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
            yield event.image_result(image_url)
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
            "message": result,
            "footer": f"今日已转运 {change_counts[user_id]['count']}/{self.max_change_times if self.max_change_times > 0 else '∞'} 次"
        })
        yield event.image_result(image_url)

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
