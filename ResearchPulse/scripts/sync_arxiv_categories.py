#!/usr/bin/env python3
"""arXiv 分类同步脚本。

本脚本从 arXiv 官方网站抓取完整的分类列表，并同步到数据库。
用于初始化或更新系统中的 arXiv 分类数据。

功能：
    1. 从 arXiv 分类页面抓取分类代码、名称和父级领域
    2. 如果网络抓取失败，使用内置的分类字典作为 fallback
    3. 将分类数据写入数据库（存在则更新，不存在则插入）

用法示例：
    # 同步分类到数据库
    cd /path/to/ResearchPulse_v2
    source .env
    python3 scripts/sync_arxiv_categories.py

依赖：
    - httpx: 用于异步 HTTP 请求
    - beautifulsoup4: 用于解析 HTML 页面（可选，抓取失败时使用内置数据）

注意：
    本脚本需要数据库连接配置（通过环境变量或 .env 文件）。
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import List, Dict

# 将项目根目录添加到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

# BeautifulSoup 用于解析 HTML，可选依赖
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# ---------------------------------------------------------------------------
# 常量定义
# ---------------------------------------------------------------------------

# arXiv 分类页面 URL
ARXIV_CATEGORIES_URL = "https://arxiv.org/category_taxonomy"

# 模块日志器
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 内置 arXiv 分类字典
# ---------------------------------------------------------------------------
# 当网络抓取失败时使用此字典作为 fallback。
# 格式：{分类代码: (分类名称, 父级领域)}
#
# 数据来源：arXiv 官方分类 taxonomy
# 最后更新：2024 年
ARXIV_CATEGORIES = {
    # ========================
    # Computer Science 计算机科学
    # ========================
    "cs.AI": ("Artificial Intelligence", "Computer Science"),
    "cs.CL": ("Computation and Language", "Computer Science"),
    "cs.CV": ("Computer Vision and Pattern Recognition", "Computer Science"),
    "cs.LG": ("Machine Learning", "Computer Science"),
    "cs.NE": ("Neural and Evolutionary Computing", "Computer Science"),
    "cs.RO": ("Robotics", "Computer Science"),
    "cs.SE": ("Software Engineering", "Computer Science"),
    "cs.DB": ("Databases", "Computer Science"),
    "cs.DC": ("Distributed, Parallel, and Cluster Computing", "Computer Science"),
    "cs.CR": ("Cryptography and Security", "Computer Science"),
    "cs.HC": ("Human-Computer Interaction", "Computer Science"),
    "cs.IR": ("Information Retrieval", "Computer Science"),
    "cs.IT": ("Information Theory", "Computer Science"),
    "cs.CY": ("Computers and Society", "Computer Science"),
    "cs.AR": ("Hardware Architecture", "Computer Science"),
    "cs.CG": ("Computational Geometry", "Computer Science"),
    "cs.FL": ("Formal Languages and Automata Theory", "Computer Science"),
    "cs.DS": ("Data Structures and Algorithms", "Computer Science"),
    "cs.CC": ("Computational Complexity", "Computer Science"),
    "cs.DL": ("Digital Libraries", "Computer Science"),
    "cs.LO": ("Logic in Computer Science", "Computer Science"),
    "cs.MA": ("Multiagent Systems", "Computer Science"),
    "cs.MM": ("Multimedia", "Computer Science"),
    "cs.NI": ("Networking and Internet Architecture", "Computer Science"),
    "cs.OS": ("Operating Systems", "Computer Science"),
    "cs.PF": ("Performance", "Computer Science"),
    "cs.PL": ("Programming Languages", "Computer Science"),
    "cs.ET": ("Emerging Technologies", "Computer Science"),
    "cs.GR": ("Graphics", "Computer Science"),
    "cs.GT": ("Computer Science and Game Theory", "Computer Science"),
    "cs.MS": ("Mathematical Software", "Computer Science"),
    "cs.NA": ("Numerical Analysis", "Computer Science"),
    "cs.OH": ("Other Computer Science", "Computer Science"),
    "cs.SI": ("Social and Information Networks", "Computer Science"),
    "cs.SD": ("Sound", "Computer Science"),
    "cs.SC": ("Symbolic Computation", "Computer Science"),
    "cs.SY": ("Systems and Control", "Computer Science"),

    # ========================
    # Mathematics 数学
    # ========================
    "math.AG": ("Algebraic Geometry", "Mathematics"),
    "math.AT": ("Algebraic Topology", "Mathematics"),
    "math.AP": ("Analysis of PDEs", "Mathematics"),
    "math.CA": ("Classical Analysis and ODEs", "Mathematics"),
    "math.CO": ("Combinatorics", "Mathematics"),
    "math.AC": ("Commutative Algebra", "Mathematics"),
    "math.CV": ("Complex Variables", "Mathematics"),
    "math.DG": ("Differential Geometry", "Mathematics"),
    "math.DS": ("Dynamical Systems", "Mathematics"),
    "math.FA": ("Functional Analysis", "Mathematics"),
    "math.GM": ("General Mathematics", "Mathematics"),
    "math.GN": ("General Topology", "Mathematics"),
    "math.GT": ("Geometric Topology", "Mathematics"),
    "math.GR": ("Group Theory", "Mathematics"),
    "math.HO": ("History and Overview", "Mathematics"),
    "math.IT": ("Information Theory", "Mathematics"),
    "math.KT": ("K-Theory and Homology", "Mathematics"),
    "math.LO": ("Logic", "Mathematics"),
    "math.MP": ("Mathematical Physics", "Mathematics"),
    "math.MG": ("Metric Geometry", "Mathematics"),
    "math.NT": ("Number Theory", "Mathematics"),
    "math.NA": ("Numerical Analysis", "Mathematics"),
    "math.OA": ("Operator Algebras", "Mathematics"),
    "math.OC": ("Optimization and Control", "Mathematics"),
    "math.PR": ("Probability", "Mathematics"),
    "math.QA": ("Quantum Algebra", "Mathematics"),
    "math.RT": ("Representation Theory", "Mathematics"),
    "math.RA": ("Rings and Algebras", "Mathematics"),
    "math.SP": ("Spectral Theory", "Mathematics"),
    "math.ST": ("Statistics Theory", "Mathematics"),
    "math.SG": ("Symplectic Geometry", "Mathematics"),

    # ========================
    # Physics 物理学
    # ========================
    # Astrophysics 天体物理
    "astro-ph.CO": ("Cosmology and Nongalactic Astrophysics", "Physics"),
    "astro-ph.EP": ("Earth and Planetary Astrophysics", "Physics"),
    "astro-ph.GA": ("Astrophysics of Galaxies", "Physics"),
    "astro-ph.HE": ("High Energy Astrophysical Phenomena", "Physics"),
    "astro-ph.IM": ("Instrumentation and Methods for Astrophysics", "Physics"),
    "astro-ph.SR": ("Solar and Stellar Astrophysics", "Physics"),
    # Condensed Matter 凝聚态物理
    "cond-mat.dis-nn": ("Disordered Systems and Neural Networks", "Physics"),
    "cond-mat.mes-hall": ("Mesoscale and Nanoscale Physics", "Physics"),
    "cond-mat.mtrl-sci": ("Materials Science", "Physics"),
    "cond-mat.other": ("Other Condensed Matter", "Physics"),
    "cond-mat.quant-gas": ("Quantum Gases", "Physics"),
    "cond-mat.soft": ("Soft Condensed Matter", "Physics"),
    "cond-mat.stat-mech": ("Statistical Mechanics", "Physics"),
    "cond-mat.str-el": ("Strongly Correlated Electrons", "Physics"),
    "cond-mat.supr-con": ("Superconductivity", "Physics"),
    # High Energy Physics 高能物理
    "gr-qc": ("General Relativity and Quantum Cosmology", "Physics"),
    "hep-ex": ("High Energy Physics - Experiment", "Physics"),
    "hep-lat": ("High Energy Physics - Lattice", "Physics"),
    "hep-ph": ("High Energy Physics - Phenomenology", "Physics"),
    "hep-th": ("High Energy Physics - Theory", "Physics"),
    "math-ph": ("Mathematical Physics", "Physics"),
    # Nonlinear Sciences 非线性科学
    "nlin.AO": ("Adaptation and Self-Organizing Systems", "Physics"),
    "nlin.CD": ("Chaotic Dynamics", "Physics"),
    "nlin.CG": ("Cellular Automata and Lattice Gases", "Physics"),
    "nlin.PS": ("Pattern Formation and Solitons", "Physics"),
    "nlin.SI": ("Exactly Solvable and Integrable Systems", "Physics"),
    # Nuclear Physics 核物理
    "nucl-ex": ("Nuclear Experiment", "Physics"),
    "nucl-th": ("Nuclear Theory", "Physics"),
    # Physics (Other) 其他物理
    "physics.acc-ph": ("Accelerator Physics", "Physics"),
    "physics.ao-ph": ("Atmospheric and Oceanic Physics", "Physics"),
    "physics.app-ph": ("Applied Physics", "Physics"),
    "physics.atm-clus": ("Atomic and Molecular Clusters", "Physics"),
    "physics.atom-ph": ("Atomic Physics", "Physics"),
    "physics.bio-ph": ("Biological Physics", "Physics"),
    "physics.chem-ph": ("Chemical Physics", "Physics"),
    "physics.class-ph": ("Classical Physics", "Physics"),
    "physics.comp-ph": ("Computational Physics", "Physics"),
    "physics.data-an": ("Data Analysis, Statistics and Probability", "Physics"),
    "physics.ed-ph": ("Physics Education", "Physics"),
    "physics.flu-dyn": ("Fluid Dynamics", "Physics"),
    "physics.gen-ph": ("General Physics", "Physics"),
    "physics.geo-ph": ("Geophysics", "Physics"),
    "physics.hist-ph": ("History and Philosophy of Physics", "Physics"),
    "physics.ins-det": ("Instrumentation and Detectors", "Physics"),
    "physics.med-ph": ("Medical Physics", "Physics"),
    "physics.optics": ("Optics", "Physics"),
    "physics.plasm-ph": ("Plasma Physics", "Physics"),
    "physics.pop-ph": ("Popular Physics", "Physics"),
    "physics.soc-ph": ("Physics and Society", "Physics"),
    "physics.space-ph": ("Space Physics", "Physics"),
    "quant-ph": ("Quantum Physics", "Physics"),

    # ========================
    # Statistics 统计学
    # ========================
    "stat.AP": ("Applications", "Statistics"),
    "stat.CO": ("Computation", "Statistics"),
    "stat.ME": ("Methodology", "Statistics"),
    "stat.ML": ("Machine Learning", "Statistics"),
    "stat.TH": ("Statistics Theory", "Statistics"),
    "stat.OT": ("Other Statistics", "Statistics"),

    # ========================
    # Electrical Engineering and Systems Science 电气工程与系统科学
    # ========================
    "eess.AS": ("Audio and Speech Processing", "Electrical Engineering"),
    "eess.IV": ("Image and Video Processing", "Electrical Engineering"),
    "eess.SP": ("Signal Processing", "Electrical Engineering"),
    "eess.SY": ("Systems and Control", "Electrical Engineering"),

    # ========================
    # Economics 经济学
    # ========================
    "econ.EM": ("Econometrics", "Economics"),
    "econ.GN": ("General Economics", "Economics"),
    "econ.TH": ("Theoretical Economics", "Economics"),

    # ========================
    # Quantitative Biology 计量生物学
    # ========================
    "q-bio.BM": ("Biomolecules", "Quantitative Biology"),
    "q-bio.CB": ("Cell Behavior", "Quantitative Biology"),
    "q-bio.GN": ("Genomics", "Quantitative Biology"),
    "q-bio.MN": ("Molecular Networks", "Quantitative Biology"),
    "q-bio.NC": ("Neurons and Cognition", "Quantitative Biology"),
    "q-bio.OT": ("Other Quantitative Biology", "Quantitative Biology"),
    "q-bio.PE": ("Populations and Evolution", "Quantitative Biology"),
    "q-bio.QM": ("Quantitative Methods", "Quantitative Biology"),
    "q-bio.SC": ("Subcellular Processes", "Quantitative Biology"),
    "q-bio.TO": ("Tissues and Organs", "Quantitative Biology"),

    # ========================
    # Quantitative Finance 计量金融
    # ========================
    "q-fin.CP": ("Computational Finance", "Quantitative Finance"),
    "q-fin.EC": ("Economics", "Quantitative Finance"),
    "q-fin.GN": ("General Finance", "Quantitative Finance"),
    "q-fin.MF": ("Mathematical Finance", "Quantitative Finance"),
    "q-fin.PM": ("Portfolio Management", "Quantitative Finance"),
    "q-fin.PR": ("Pricing of Securities", "Quantitative Finance"),
    "q-fin.RM": ("Risk Management", "Quantitative Finance"),
    "q-fin.ST": ("Statistical Finance", "Quantitative Finance"),
    "q-fin.TR": ("Trading and Market Microstructure", "Quantitative Finance"),
}


async def fetch_categories_from_web() -> Dict[str, tuple]:
    """从 arXiv 网站抓取分类列表。

    访问 arXiv 分类页面，解析 HTML 获取完整的分类代码、名称和父级领域。

    返回：
        Dict[str, tuple]: 分类字典，格式为 {分类代码: (分类名称, 父级领域)}。
                         如果抓取失败，返回空字典。

    异常：
        所有异常都会被捕获并记录日志，函数返回空字典。
    """
    try:
        # 使用 httpx 发送异步 HTTP 请求
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(ARXIV_CATEGORIES_URL)
            response.raise_for_status()

        # 使用 BeautifulSoup 解析 HTML
        soup = BeautifulSoup(response.text, "html.parser")
        categories = {}

        # 解析分类页面结构
        # 页面使用 accordion 结构组织分类
        for div in soup.find_all("div", class_="accordion"):
            # 获取主分类名称（如 "Computer Science"）
            main_header = div.find("h2")
            if not main_header:
                continue
            main_category = main_header.get_text(strip=True)

            # 遍历子分类
            for item in div.find_all("div", class_="column"):
                link = item.find("a")
                if not link:
                    continue
                # 分类代码（如 "cs.AI"）
                code = link.get_text(strip=True)
                # 分类名称
                name = item.find("span", class_="name")
                name_text = name.get_text(strip=True) if name else code

                if code and name_text:
                    categories[code] = (name_text, main_category)

        return categories

    except Exception as e:
        logger.warning(f"Failed to fetch categories from web: {e}")
        return {}


def get_all_categories() -> Dict[str, tuple]:
    """获取所有已知的 arXiv 分类。

    返回内置分类字典的副本，不包含从网络抓取的分类。

    返回：
        Dict[str, tuple]: 分类字典的副本。
    """
    return ARXIV_CATEGORIES.copy()


async def sync_categories_to_db():
    """将分类数据同步到数据库。

    执行流程：
        1. 尝试从 arXiv 网站抓取最新分类
        2. 合并网络抓取的分类和内置分类（内置优先）
        3. 逐个插入或更新数据库中的分类记录

    数据库操作：
        - 如果分类代码已存在，更新名称和父级
        - 如果分类代码不存在，插入新记录

    返回：
        None: 本函数无返回值。

    注意：
        需要配置数据库连接（通过环境变量或 .env 文件）。
    """
    from core.database import get_session_factory
    from apps.crawler.models import ArxivCategory
    from sqlalchemy import select

    # 尝试从网络抓取分类
    web_categories = await fetch_categories_from_web()

    # 合并分类：内置分类优先（覆盖网络抓取的同名分类）
    all_categories = {**web_categories, **ARXIV_CATEGORIES}

    logger.info(f"Total categories to sync: {len(all_categories)}")

    # 获取数据库会话工厂
    factory = get_session_factory()

    async with factory() as session:
        for code, (name, parent) in all_categories.items():
            # 检查分类是否已存在
            result = await session.execute(
                select(ArxivCategory).where(ArxivCategory.code == code)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # 更新现有记录
                existing.name = name
                existing.parent_code = parent
            else:
                # 插入新记录
                category = ArxivCategory(
                    code=code,
                    name=name,
                    parent_code=parent,
                    is_active=True,
                )
                session.add(category)

        # 提交事务
        await session.commit()

    logger.info(f"Synced {len(all_categories)} categories to database")


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # 执行同步
    asyncio.run(sync_categories_to_db())
