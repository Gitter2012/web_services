# =============================================================================
# 模块: apps/daily_report/formatters/wechat_html.py
# 功能: 微信公众号 HTML 格式化器
# 架构角色: 将 Markdown 报告转换为微信公众号兼容的 HTML 内容
# 设计决策:
#   1. 微信公众号编辑器支持 HTML 子集（不支持 JS、外部 CSS）
#   2. 所有样式必须使用内联 style 属性
#   3. 图片 URL 必须来自微信服务器（外部图片会被过滤）
#   4. 正文限制：< 20000 字符，< 1MB
#   5. 基于 Markdown 结构直接生成 HTML，不依赖第三方 Markdown 转 HTML 库
# =============================================================================

"""WeChat Official Account HTML formatter.

Converts Markdown report content to WeChat-compatible HTML with inline styles.
"""

from __future__ import annotations

import html
import re
from typing import Any

from .base import BaseFormatter


class WeChatHTMLFormatter(BaseFormatter):
    """Formatter that converts Markdown report to WeChat MP HTML.

    微信公众号 HTML 格式化器。

    微信公众号对 HTML 的限制：
    - 不支持 JavaScript
    - 不支持 <link>/<style> 标签引入外部 CSS（但部分客户端支持内联 <style>）
    - 推荐使用内联 style 属性确保兼容性
    - 外部图片 URL 会被过滤，正文图片必须使用微信 CDN
    - 正文最大 20000 字符 / 1MB
    """

    # 微信公众号常用配色
    STYLE = {
        "title_color": "#1a1a1a",
        "subtitle_color": "#3e3e3e",
        "section_title_color": "#1e6bb8",
        "text_color": "#3e3e3e",
        "meta_color": "#888888",
        "link_color": "#576b95",
        "border_color": "#e5e5e5",
        "bg_light": "#f7f7f7",
        "accent_color": "#1e6bb8",
    }

    def format(self, content: str, truncate: bool = False, max_length: int = 19000) -> str:
        """Format Markdown content to WeChat-compatible HTML.

        将 Markdown 报告转换为微信公众号 HTML。

        Args:
            content: Markdown report content.
            truncate: Whether to truncate content when exceeding max_length.
                      Default is False (no truncation).
            max_length: Maximum character length when truncate is True.
                        Default is 19000 (WeChat limit is 20000).

        Returns:
            WeChat-compatible HTML string.
        """
        if not content:
            return ""

        lines = content.split("\n")
        html_parts: list[str] = []
        in_blockquote = False
        in_summary = False

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # 空行
            if not stripped:
                if in_blockquote:
                    in_blockquote = False
                if in_summary:
                    html_parts.append("</p>")
                    in_summary = False
                i += 1
                continue

            # 分隔线 ---
            if stripped == "---":
                html_parts.append(
                    f'<hr style="border:none;border-top:1px solid {self.STYLE["border_color"]};'
                    f'margin:20px 0;" />'
                )
                i += 1
                continue

            # H1 标题（报告主标题）- 跳过，由微信草稿标题字段处理
            if stripped.startswith("# ") and not stripped.startswith("## "):
                # 不输出 H1，微信草稿的 title 字段已包含
                i += 1
                continue

            # H2 标题（章节标题，如 "📌 论文列表"）
            if stripped.startswith("## "):
                title_text = self._escape(stripped[3:])
                html_parts.append(
                    f'<h2 style="font-size:18px;color:{self.STYLE["section_title_color"]};'
                    f'font-weight:bold;margin:24px 0 12px 0;padding-bottom:8px;'
                    f'border-bottom:2px solid {self.STYLE["accent_color"]};">'
                    f'{title_text}</h2>'
                )
                i += 1
                continue

            # H3 标题（论文标题，如 "1. 标题"）
            if stripped.startswith("### "):
                title_text = stripped[4:]
                title_html = self._inline_format(title_text)
                html_parts.append(
                    f'<h3 style="font-size:16px;color:{self.STYLE["subtitle_color"]};'
                    f'font-weight:bold;margin:18px 0 8px 0;line-height:1.5;">'
                    f'{title_html}</h3>'
                )
                i += 1
                continue

            # 引用块 >
            if stripped.startswith("> "):
                quote_text = self._escape(stripped[2:])
                html_parts.append(
                    f'<blockquote style="margin:12px 0;padding:10px 16px;'
                    f'background:{self.STYLE["bg_light"]};border-left:4px solid '
                    f'{self.STYLE["accent_color"]};color:{self.STYLE["meta_color"]};'
                    f'font-size:14px;line-height:1.6;">{quote_text}</blockquote>'
                )
                i += 1
                continue

            # 无序列表项 -
            if stripped.startswith("- "):
                item_text = self._inline_format(stripped[2:])
                html_parts.append(
                    f'<p style="margin:4px 0 4px 16px;padding-left:8px;'
                    f'color:{self.STYLE["text_color"]};font-size:14px;line-height:1.6;'
                    f'border-left:2px solid {self.STYLE["border_color"]};">'
                    f'{item_text}</p>'
                )
                i += 1
                continue

            # 元信息行（以 **xxx**: 开头，如 **作者**: xxx）
            if stripped.startswith("**") and "**:" in stripped:
                meta_html = self._format_meta_line(stripped)
                html_parts.append(meta_html)
                i += 1
                continue

            # 斜体行（如 *由 ResearchPulse 自动生成*）
            if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
                italic_text = self._escape(stripped.strip("*"))
                html_parts.append(
                    f'<p style="margin:4px 0;color:{self.STYLE["meta_color"]};'
                    f'font-size:12px;font-style:italic;text-align:center;">'
                    f'{italic_text}</p>'
                )
                i += 1
                continue

            # 摘要标签行 **摘要**:
            if stripped == "**摘要**:":
                html_parts.append(
                    f'<p style="margin:8px 0 4px 0;font-weight:bold;'
                    f'color:{self.STYLE["subtitle_color"]};font-size:14px;">摘要：</p>'
                )
                i += 1
                continue

            # 普通段落文本（摘要内容等）
            para_text = self._inline_format(stripped)
            html_parts.append(
                f'<p style="margin:6px 0;color:{self.STYLE["text_color"]};'
                f'font-size:14px;line-height:1.8;text-align:justify;">'
                f'{para_text}</p>'
            )
            i += 1

        result = "\n".join(html_parts)

        # 检查内容长度限制（仅在启用截断时）
        if truncate and len(result) > max_length:
            result = self._truncate_html(result, max_length)

        return result

    def generate_digest(self, report: Any, max_length: int = 128) -> str:
        """Generate a digest string for the draft article.

        生成草稿文章摘要（最多 128 字）。

        Args:
            report: DailyReport instance.
            max_length: Maximum digest length.

        Returns:
            Digest string.
        """
        category_name = getattr(report, "category_name", report.category)
        article_count = getattr(report, "article_count", 0)
        report_date = report.report_date

        digest = (
            f"{report_date.strftime('%m月%d日')} {category_name}领域"
            f"收录 {article_count} 篇最新 arXiv 论文"
        )

        if len(digest) > max_length:
            digest = digest[: max_length - 3] + "..."

        return digest

    # ========================================================================
    # 内部辅助方法
    # ========================================================================

    def _escape(self, text: str) -> str:
        """HTML-escape text.

        对文本进行 HTML 转义。
        """
        return html.escape(text, quote=True)

    def _inline_format(self, text: str) -> str:
        """Process inline Markdown formatting (bold, italic, links).

        处理行内 Markdown 格式：粗体、斜体、链接。

        Args:
            text: Raw Markdown text.

        Returns:
            HTML-formatted string.
        """
        # 先转义 HTML 特殊字符
        result = self._escape(text)

        # 还原被转义的 Markdown 语法标记
        # 处理链接 [text](url) - 需要在转义后处理
        result = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            lambda m: (
                f'<a style="color:{self.STYLE["link_color"]};text-decoration:none;" '
                f'href="{m.group(2)}">{m.group(1)}</a>'
            ),
            result,
        )

        # 处理粗体 **text**
        result = re.sub(
            r'\*\*([^*]+)\*\*',
            r'<strong>\1</strong>',
            result,
        )

        # 处理斜体 *text*
        result = re.sub(
            r'(?<!\*)\*([^*]+)\*(?!\*)',
            r'<em>\1</em>',
            result,
        )

        return result

    def _format_meta_line(self, line: str) -> str:
        """Format a metadata line like **作者**: xxx.

        格式化元信息行（如 **作者**: xxx, **链接**: [arXiv](url)）。

        Args:
            line: Raw Markdown metadata line.

        Returns:
            HTML-formatted metadata line.
        """
        # 解析 **label**: value 格式
        match = re.match(r'\*\*([^*]+)\*\*:\s*(.*)', line)
        if not match:
            return (
                f'<p style="margin:4px 0;color:{self.STYLE["text_color"]};'
                f'font-size:14px;">{self._inline_format(line)}</p>'
            )

        label = self._escape(match.group(1))
        value = match.group(2).strip()
        value_html = self._inline_format(value)

        return (
            f'<p style="margin:4px 0;color:{self.STYLE["text_color"]};'
            f'font-size:13px;line-height:1.6;">'
            f'<strong style="color:{self.STYLE["subtitle_color"]};">{label}：</strong>'
            f'{value_html}</p>'
        )

    def _truncate_html(self, html_content: str, max_length: int) -> str:
        """Truncate HTML content to stay within length limit.

        截断 HTML 内容以满足长度限制。
        简单策略：从末尾开始移除完整的 HTML 元素。

        Args:
            html_content: Full HTML content.
            max_length: Maximum character length.

        Returns:
            Truncated HTML content.
        """
        if len(html_content) <= max_length:
            return html_content

        # 找到最后一个完整标签的位置
        truncated = html_content[:max_length]

        # 确保不在标签中间截断
        last_close = truncated.rfind("</")
        if last_close > 0:
            # 找到这个关闭标签的结束位置
            end = truncated.find(">", last_close)
            if end > 0:
                truncated = truncated[: end + 1]

        # 添加截断提示
        truncated += (
            f'\n<p style="margin:16px 0;color:{self.STYLE["meta_color"]};'
            f'font-size:13px;text-align:center;font-style:italic;">'
            f'（内容过长，部分论文未显示）</p>'
        )

        return truncated
