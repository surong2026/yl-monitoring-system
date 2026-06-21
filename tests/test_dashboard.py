"""
Streamlit 仪表盘测试

覆盖:
1. 模块文件存在性
2. 数据库集成
3. 页面函数类型正确
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from src.database.models import get_engine, init_db, MonitoringSite, MonitoringRecord
from datetime import date


@pytest.fixture
def seeded_session():
    eng = get_engine("sqlite:///:memory:")
    init_db(eng)
    from src.database.models import get_session
    session = get_session(eng)

    site = MonitoringSite(
        site_code="YL-WS-001", site_name="测试站",
        element_type="water_surface", district="玉州区",
    )
    session.add(site)
    session.flush()

    for code, val in [("pH", 7.3), ("DO", 7.1), ("COD", 12.0), ("NH3N", 0.35), ("TP", 0.08)]:
        session.add(MonitoringRecord(
            site_id=site.id, sample_date=date(2026, 1, 15),
            element_type="water_surface", parameter_code=code,
            parameter_name=code, value=val
        ))
    session.commit()
    return session


class TestAppStructure:
    def test_app_file_exists(self):
        """app.py 文件存在"""
        path = PROJECT_ROOT / "src" / "web" / "app.py"
        assert path.exists(), f"app.py not found at {path}"

    def test_app_contains_pages(self):
        """app.py 包含四个页面"""
        path = PROJECT_ROOT / "src" / "web" / "app.py"
        content = path.read_text(encoding="utf-8")
        assert "def page_overview" in content
        assert "def page_import" in content
        assert "def page_assessment" in content
        assert "def page_reports" in content

    def test_app_has_main(self):
        """app.py 包含主入口"""
        path = PROJECT_ROOT / "src" / "web" / "app.py"
        content = path.read_text(encoding="utf-8")
        assert "PAGES[" in content or "selected_page" in content

    def test_init_has_docstring(self):
        """__init__.py 有正确文档"""
        path = PROJECT_ROOT / "src" / "web" / "__init__.py"
        content = path.read_text(encoding="utf-8")
        assert "streamlit" in content.lower()


class TestDatabaseIntegration:
    def test_seeded_data(self, seeded_session):
        """种子数据正确入库"""
        sites = seeded_session.query(MonitoringSite).all()
        assert len(sites) == 1
        assert sites[0].site_code == "YL-WS-001"

    def test_records_count(self, seeded_session):
        """5条记录正确入库"""
        records = seeded_session.query(MonitoringRecord).all()
        assert len(records) == 5

    def test_record_values(self, seeded_session):
        """记录值正确"""
        ph = seeded_session.query(MonitoringRecord).filter_by(parameter_code="pH").first()
        assert ph is not None
        assert ph.value == 7.3
