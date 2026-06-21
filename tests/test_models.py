"""数据库模型单元测试"""

import pytest
from src.database.models import (
    Base, MonitoringSite, MonitoringRecord,
    QualityStandard, AssessmentResult, Report,
    get_engine, init_db
)


@pytest.fixture
def engine():
    """创建内存数据库"""
    eng = get_engine("sqlite:///:memory:")
    init_db(eng)
    return eng


def test_models_import():
    """验证所有模型可导入"""
    assert MonitoringSite.__tablename__ == "monitoring_sites"
    assert MonitoringRecord.__tablename__ == "monitoring_records"
    assert QualityStandard.__tablename__ == "quality_standards"
    assert AssessmentResult.__tablename__ == "assessment_results"
    assert Report.__tablename__ == "reports"


def test_create_site(engine):
    """验证创建点位"""
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        site = MonitoringSite(
            site_code="YL-WS-001",
            site_name="南流江六司段",
            element_type="water_surface",
            longitude=110.18,
            latitude=22.64,
            district="玉州区",
            river_basin="南流江",
            section_type="国控"
        )
        session.add(site)
        session.commit()
        assert site.id is not None
