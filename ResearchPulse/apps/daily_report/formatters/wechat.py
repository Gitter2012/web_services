# =============================================================================
# 模块: apps/daily_report/formatters/wechat.py
# 功能: 微信公众号格式化器
# 架构角色: 将 Markdown 转换为微信公众号兼容格式
# =============================================================================

"""WeChat public account formatter."""

from __future__ import annotations

import re

from .base import BaseFormatter


class WeChatFormatter(BaseFormatter):
    """Formatter for WeChat public account (微信公众号).

    微信公众号格式化器。

    微信公众号对 Markdown 的支持有限，需要进行以下转换：
    1. 链接格式：微信公众号不支持 [text](url) 格式，需要转换为纯文本或特殊格式
    2. 标题样式：微信公众号有自己的标题样式
    3. 分隔线：简化处理
    4. 强调样式：确保粗体、斜体正确显示
    """

    def format(self, content: str) -> str:
        """Format Markdown content for WeChat public account.

        将 Markdown 格式转换为微信公众号兼容格式。

        Args:
            content: Markdown content.

        Returns:
            WeChat-compatible content string.
        """
        if not content:
            return content

        lines = content.split("\n")
        result_lines = []

        for line in lines:
            # 处理链接：将 [text](url) 转换为 "text: url" 格式
            # 微信公众号不支持 Markdown 链接语法
            line = self._convert_links(line)

            # 处理标题
            line = self._convert_headers(line)

            # 处理分隔线
            line = self._convert_hr(line)

            result_lines.append(line)

        return "\n".join(result_lines)

    def _convert_links(self, line: str) -> str:
        """Convert Markdown links to WeChat format.

        转换 Markdown 链接格式。
        微信公众号不支持 [text](url) 格式，转换为：
        - 如果是 arXiv 链接，保留为 "arXiv: xxx" 格式
        - 其他链接，转换为 "text: url" 格式
        """
        # 匹配 [text](url) 格式
        pattern = r'\[([^\]]+)\]\(([^)]+)\)'

        def replace_link(match):
            text = match.group(1)
            url = match.group(2)

            # arXiv 链接特殊处理
            if "arxiv.org" in url or text.startswith("arXiv"):
                return f"arXiv: {url}"

            # 其他链接
            return f"{text}: {url}"

        return re.sub(pattern, replace_link, line)

    def _convert_headers(self, line: str) -> str:
        """Convert Markdown headers.

        转换 Markdown 标题。
        微信公众号支持 H1-H3，但样式有限。
        这里保持原有格式，微信编辑器会处理。
        """
        # 微信公众号可以识别 # 开头的标题
        # 但建议最多使用三级标题
        if line.startswith("#### "):
            # 四级及以上标题转为粗体
            return f"**{line[5:]}**"
        return line

    def _convert_hr(self, line: str) -> str:
        """Convert horizontal rules.

        转换分隔线。
        微信公众号可能不识别 --- 分隔线，转换为空行+特殊符号。
        """
        if line.strip() == "---":
            return "\n——————————\n"
        return line

    def format_simple(self, content: str) -> str:
        """Simple formatting for quick copy-paste.

        简单格式化，适合快速复制粘贴。

        移除所有 Markdown 语法，只保留纯文本。
        """
        if not content:
            return content

        # 移除标题标记
        content = re.sub(r'^#{1,6}\s*', '', content, flags=re.MULTILINE)

        # 移除粗体/斜体标记
        content = re.sub(r'\*\*([^*]+)\*\*', r'\1', content)
        content = re.sub(r'\*([^*]+)\*', r'\1', content)
        content = re.sub(r'__([^_]+)__', r'\1', content)
        content = re.sub(r'_([^_]+)_', r'\1', content)

        # 转换链接
        content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1: \2', content)

        # 移除多余空行
        content = re.sub(r'\n{3,}', '\n\n', content)

        return content.strip()
