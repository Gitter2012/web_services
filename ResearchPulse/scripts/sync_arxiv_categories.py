"""ArXiv category scraper for ResearchPulse v2.

This script fetches the complete list of arXiv categories from the official
arXiv website and inserts them into the database.

Usage:
    cd /path/to/ResearchPulse_v2
    source .env
    python3 scripts/sync_arxiv_categories.py
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import List, Dict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# ArXiv category page URL
ARXIV_CATEGORIES_URL = "https://arxiv.org/category_taxonomy"

# Logger for this module
logger = logging.getLogger(__name__)

# Known arXiv categories (fallback if scraping fails)
ARXIV_CATEGORIES = {
    # Computer Science
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

    # Mathematics
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

    # Physics
    "astro-ph.CO": ("Cosmology and Nongalactic Astrophysics", "Physics"),
    "astro-ph.EP": ("Earth and Planetary Astrophysics", "Physics"),
    "astro-ph.GA": ("Astrophysics of Galaxies", "Physics"),
    "astro-ph.HE": ("High Energy Astrophysical Phenomena", "Physics"),
    "astro-ph.IM": ("Instrumentation and Methods for Astrophysics", "Physics"),
    "astro-ph.SR": ("Solar and Stellar Astrophysics", "Physics"),
    "cond-mat.dis-nn": ("Disordered Systems and Neural Networks", "Physics"),
    "cond-mat.mes-hall": ("Mesoscale and Nanoscale Physics", "Physics"),
    "cond-mat.mtrl-sci": ("Materials Science", "Physics"),
    "cond-mat.other": ("Other Condensed Matter", "Physics"),
    "cond-mat.quant-gas": ("Quantum Gases", "Physics"),
    "cond-mat.soft": ("Soft Condensed Matter", "Physics"),
    "cond-mat.stat-mech": ("Statistical Mechanics", "Physics"),
    "cond-mat.str-el": ("Strongly Correlated Electrons", "Physics"),
    "cond-mat.supr-con": ("Superconductivity", "Physics"),
    "gr-qc": ("General Relativity and Quantum Cosmology", "Physics"),
    "hep-ex": ("High Energy Physics - Experiment", "Physics"),
    "hep-lat": ("High Energy Physics - Lattice", "Physics"),
    "hep-ph": ("High Energy Physics - Phenomenology", "Physics"),
    "hep-th": ("High Energy Physics - Theory", "Physics"),
    "math-ph": ("Mathematical Physics", "Physics"),
    "nlin.AO": ("Adaptation and Self-Organizing Systems", "Physics"),
    "nlin.CD": ("Chaotic Dynamics", "Physics"),
    "nlin.CG": ("Cellular Automata and Lattice Gases", "Physics"),
    "nlin.PS": ("Pattern Formation and Solitons", "Physics"),
    "nlin.SI": ("Exactly Solvable and Integrable Systems", "Physics"),
    "nucl-ex": ("Nuclear Experiment", "Physics"),
    "nucl-th": ("Nuclear Theory", "Physics"),
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

    # Statistics
    "stat.AP": ("Applications", "Statistics"),
    "stat.CO": ("Computation", "Statistics"),
    "stat.ME": ("Methodology", "Statistics"),
    "stat.ML": ("Machine Learning", "Statistics"),
    "stat.TH": ("Statistics Theory", "Statistics"),
    "stat.OT": ("Other Statistics", "Statistics"),

    # Electrical Engineering and Systems Science
    "eess.AS": ("Audio and Speech Processing", "Electrical Engineering"),
    "eess.IV": ("Image and Video Processing", "Electrical Engineering"),
    "eess.SP": ("Signal Processing", "Electrical Engineering"),
    "eess.SY": ("Systems and Control", "Electrical Engineering"),

    # Economics
    "econ.EM": ("Econometrics", "Economics"),
    "econ.GN": ("General Economics", "Economics"),
    "econ.TH": ("Theoretical Economics", "Economics"),

    # Quantitative Biology
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

    # Quantitative Finance
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
    """Fetch category taxonomy from the arXiv website.

    从 arXiv 分类页面抓取分类代码、名称与父级领域。

    Returns:
        Dict[str, tuple]: Mapping of category code to (name, parent).
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(ARXIV_CATEGORIES_URL)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        categories = {}

        # Parse the category taxonomy page
        for div in soup.find_all("div", class_="accordion"):
            # Main category (e.g., "Computer Science")
            main_header = div.find("h2")
            if not main_header:
                continue
            main_category = main_header.get_text(strip=True)

            # Subcategories
            for item in div.find_all("div", class_="column"):
                link = item.find("a")
                if not link:
                    continue
                code = link.get_text(strip=True)
                name = item.find("span", class_="name")
                name_text = name.get_text(strip=True) if name else code

                if code and name_text:
                    categories[code] = (name_text, main_category)

        return categories

    except Exception as e:
        logger.warning(f"Failed to fetch categories from web: {e}")
        return {}


def get_all_categories() -> Dict[str, tuple]:
    """Return all known arXiv categories.

    返回内置的 arXiv 分类字典副本。

    Returns:
        Dict[str, tuple]: Mapping of category code to (name, parent).
    """
    return ARXIV_CATEGORIES.copy()


async def sync_categories_to_db():
    """Sync all categories to the database.

    将分类数据写入数据库，已存在则更新名称与父级。

    Returns:
        None: This function does not return a value.
    """
    from core.database import get_session_factory
    from apps.crawler.models import ArxivCategory
    from sqlalchemy import select

    # Try to fetch from web first
    web_categories = await fetch_categories_from_web()

    # Merge with known categories (known takes precedence)
    all_categories = {**web_categories, **ARXIV_CATEGORIES}

    logger.info(f"Total categories to sync: {len(all_categories)}")

    factory = get_session_factory()

    async with factory() as session:
        for code, (name, parent) in all_categories.items():
            # Check if exists
            result = await session.execute(
                select(ArxivCategory).where(ArxivCategory.code == code)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update
                existing.name = name
                existing.parent_code = parent
            else:
                # Insert
                category = ArxivCategory(
                    code=code,
                    name=name,
                    parent_code=parent,
                    is_active=True,
                )
                session.add(category)

        await session.commit()

    logger.info(f"Synced {len(all_categories)} categories to database")


if __name__ == "__main__":
    asyncio.run(sync_categories_to_db())
