# =============================================================================
# Sphinx 配置文件
# =============================================================================
# ResearchPulse 项目文档构建配置
#
# 使用方法:
#   pip install sphinx sphinx-rtd-theme
#   cd docs && sphinx-build -b html . _build/html
#
# 生成 PDF:
#   pip install sphinx-latexpdf
#   sphinx-build -b latex . _build/latex
# =============================================================================

from __future__ import annotations
import os
import sys

# 项目根目录（相对于本配置文件）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

# 项目信息
project = "ResearchPulse"
copyright = "2024-2026, ResearchPulse Team"
author = "ResearchPulse Team"
version = "2.0.0"
release = "2.0.0"

# 扩展配置
extensions = [
    # 基础扩展
    "sphinx.ext.autodoc",          # 自动从 docstring 生成文档
    "sphinx.ext.viewcode",         # 在文档中显示源代码链接
    "sphinx.ext.intersphinx",      # 跨项目链接
    "sphinx.ext.napoleon",         # NumPy/Google 风格的 docstring
    "myst_parser",                 # Markdown 支持
    # 功能扩展
    "sphinx.ext.todo",             # TODO 标记
    "sphinx.ext.coverage",         # 覆盖率报告
    "sphinx.ext.imgmath",          # 数学公式渲染
    "sphinx.ext.ifconfig",         # 条件内容
    "sphinx.ext.autosummary",      # 自动摘要
]

# Napoleon 扩展配置（支持 Google 和 NumPy 风格的 docstring）
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_type_aliases = None

# Autodoc 配置
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__,__dict__",
    "inherited-members": False,
    "show-inheritance": True,
}

autodoc_class_signature = "separated"
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autosummary_generate = True

# 模板配置
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# HTML 输出配置
html_theme = "sphinx_rtd_theme"
html_static_path = []

# HTML 主题选项
html_theme_options = {
    "canonical_url": "",
    "analytics_id": "",
    "display_version": True,
    "prev_next_buttons_location": "bottom",
    "style_external_links": False,
    "style_nav_header_background": "#2980b9",
    "toc_options": {
        "collapsible": True,
    },
}

# LaTeX 输出配置（用于 PDF 生成）
latex_engine = "pdflatex"
latex_elements = {
    "preamble": r"""
\usepackage{xeCJK}
\setCJKmainfont{Noto Sans CJK SC}
""",
    "figure_align": "htbp",
}

latex_documents = [
    ("index", "researchpulse.tex", "ResearchPulse Documentation", "ResearchPulse Team", "manual"),
]

# Intersphinx 配置
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "fastapi": ("https://fastapi.tiangolo.com", None),
    "sqlalchemy": ("https://docs.sqlalchemy.org", None),
    "httpx": ("https://www.python-httpx.org", None),
}

# 源文件配置
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# Master document
master_doc = "index"

# 输出目录
build_dir = os.path.join(os.path.dirname(__file__), "_build")

# 警告配置
suppress_warnings = ["autodoc.import_cycle"]
