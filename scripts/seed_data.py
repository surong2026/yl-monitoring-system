"""
种子数据生成 — 玉林市南流江 4 个国控断面 2026年1月监测数据

用于验证水质评价引擎和 Streamlit 仪表盘。
"""

import sys
from pathlib import Path

# 项目根加入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date
from src.database.models import (
    get_engine, init_db, get_session,
    MonitoringSite, MonitoringRecord
)
from src.analysis.quality_assessment import WaterQualityAssessor, QualityClass


def create_sites(session):
    """创建 4 个南流江断面"""
    sites = [
        {
            "site_code": "YL-WS-001",
            "site_name": "南流江六司段",
            "element_type": "water_surface",
            "longitude": 110.18, "latitude": 22.64,
            "district": "玉州区",
            "river_basin": "南流江",
            "section_type": "国控",
        },
        {
            "site_code": "YL-WS-002",
            "site_name": "南流江横山段",
            "element_type": "water_surface",
            "longitude": 110.15, "latitude": 22.58,
            "district": "玉州区",
            "river_basin": "南流江",
            "section_type": "国控",
        },
        {
            "site_code": "YL-WS-003",
            "site_name": "南流江沙河段",
            "element_type": "water_surface",
            "longitude": 109.98, "latitude": 22.45,
            "district": "博白县",
            "river_basin": "南流江",
            "section_type": "国控",
        },
        {
            "site_code": "YL-WS-004",
            "site_name": "南流江合浦段",
            "element_type": "water_surface",
            "longitude": 109.78, "latitude": 22.32,
            "district": "博白县",
            "river_basin": "南流江",
            "section_type": "省控",
        },
    ]

    for s in sites:
        existing = session.query(MonitoringSite).filter_by(site_code=s["site_code"]).first()
        if not existing:
            session.add(MonitoringSite(**s))

    session.commit()
    return session.query(MonitoringSite).all()


def create_records(session):
    """生成 2026年1月监测数据 (含超标案例)"""

    # 每个断面的参数值 {site_code: {param: value}}
    # 断面1 (六司段): 全部达标
    # 断面2 (横山段): NH3_N, TP 超标
    # 断面3 (沙河段): COD 超标
    # 断面4 (合浦段): 全部达标
    data = {
        "YL-WS-001": {
            "pH": 7.3, "DO": 7.1, "COD": 12.0, "BOD5": 2.5,
            "NH3N": 0.35, "TP": 0.08, "TN": 1.2, "Cu": 0.005,
            "Zn": 0.02, "F": 0.5, "As": 0.002, "Hg": 0.00003,
            "Cd": 0.001, "Cr6": 0.02, "Pb": 0.01, "CN": 0.005,
            "VPH": 0.002, "LAS": 0.1, "S2": 0.05, "FC": 5000,
        },
        "YL-WS-002": {
            "pH": 7.1, "DO": 4.2, "COD": 18.0, "BOD5": 3.5,
            "NH3N": 2.1, "TP": 0.32, "TN": 2.8, "Cu": 0.008,
            "Zn": 0.03, "F": 0.6, "As": 0.003, "Hg": 0.00005,
            "Cd": 0.002, "Cr6": 0.03, "Pb": 0.015, "CN": 0.005,
            "VPH": 0.003, "LAS": 0.2, "S2": 0.08, "FC": 15000,
        },
        "YL-WS-003": {
            "pH": 7.5, "DO": 5.5, "COD": 25.0, "BOD5": 4.5,
            "NH3N": 0.8, "TP": 0.18, "TN": 1.8, "Cu": 0.006,
            "Zn": 0.025, "F": 0.55, "As": 0.0025, "Hg": 0.00004,
            "Cd": 0.0015, "Cr6": 0.025, "Pb": 0.012, "CN": 0.004,
            "VPH": 0.002, "LAS": 0.15, "S2": 0.06, "FC": 8000,
        },
        "YL-WS-004": {
            "pH": 7.4, "DO": 6.8, "COD": 10.0, "BOD5": 2.0,
            "NH3N": 0.25, "TP": 0.05, "TN": 0.9, "Cu": 0.004,
            "Zn": 0.015, "F": 0.4, "As": 0.0015, "Hg": 0.00002,
            "Cd": 0.0008, "Cr6": 0.015, "Pb": 0.008, "CN": 0.003,
            "VPH": 0.001, "LAS": 0.08, "S2": 0.04, "FC": 3000,
        },
    }

    sample_date = date(2026, 1, 15)
    report_no = "YL-202601-W"

    # 参数名称映射 (JSON标准库里的 code → 中文名)
    param_names = {
        "pH": "pH值", "DO": "溶解氧", "COD": "化学需氧量", "BOD5": "五日生化需氧量",
        "NH3N": "氨氮", "TP": "总磷", "TN": "总氮", "Cu": "铜",
        "Zn": "锌", "F": "氟化物", "As": "砷", "Hg": "汞",
        "Cd": "镉", "Cr6": "六价铬", "Pb": "铅", "CN": "氰化物",
        "VPH": "挥发酚", "LAS": "阴离子表面活性剂", "S2": "硫化物", "FC": "粪大肠菌群",
    }
    param_units = {
        "pH": "无量纲", "DO": "mg/L", "COD": "mg/L", "BOD5": "mg/L",
        "NH3N": "mg/L", "TP": "mg/L", "TN": "mg/L", "Cu": "mg/L",
        "Zn": "mg/L", "F": "mg/L", "As": "mg/L", "Hg": "mg/L",
        "Cd": "mg/L", "Cr6": "mg/L", "Pb": "mg/L", "CN": "mg/L",
        "VPH": "mg/L", "LAS": "mg/L", "S2": "mg/L", "FC": "个/L",
    }

    # 检出限
    detection_limits = {
        "Hg": 0.00004, "Cd": 0.001, "As": 0.002, "CN": 0.004,
        "VPH": 0.003, "Pb": 0.01,
    }

    for site_code, params in data.items():
        site = session.query(MonitoringSite).filter_by(site_code=site_code).first()
        if not site:
            print(f"警告: 站点 {site_code} 不存在, 跳过")
            continue

        for param_code, value in params.items():
            # 检查检出限
            dl = detection_limits.get(param_code)
            is_detected = True
            if dl and value < dl:
                is_detected = False

            record = MonitoringRecord(
                site_id=site.id,
                sample_date=sample_date,
                element_type="water_surface",
                parameter_code=param_code,
                parameter_name=param_names.get(param_code, param_code),
                parameter_unit=param_units.get(param_code, ""),
                value=value,
                detection_limit=dl,
                is_detected=is_detected,
                standard_code="GB3838-2002",
                report_no=report_no,
            )
            session.add(record)

    session.commit()
    return session.query(MonitoringRecord).count()


def run_assessment():
    """在内存中跑一遍评价 (不写数据库)"""
    assessor = WaterQualityAssessor()

    data = {
        "YL-WS-001": {
            "pH": 7.3, "DO": 7.1, "COD": 12.0, "BOD5": 2.5,
            "NH3N": 0.35, "TP": 0.08, "TN": 1.2, "Cu": 0.005,
            "Zn": 0.02, "F": 0.5, "As": 0.002, "Hg": 0.00003,
            "Cd": 0.001, "Cr6": 0.02, "Pb": 0.01, "CN": 0.005,
            "VPH": 0.002, "LAS": 0.1, "S2": 0.05, "FC": 5000,
        },
        "YL-WS-002": {
            "pH": 7.1, "DO": 4.2, "COD": 18.0, "BOD5": 3.5,
            "NH3N": 2.1, "TP": 0.32, "TN": 2.8, "Cu": 0.008,
            "Zn": 0.03, "F": 0.6, "As": 0.003, "Hg": 0.00005,
            "Cd": 0.002, "Cr6": 0.03, "Pb": 0.015, "CN": 0.005,
            "VPH": 0.003, "LAS": 0.2, "S2": 0.08, "FC": 15000,
        },
    }

    site_names = {
        "YL-WS-001": "南流江六司段",
        "YL-WS-002": "南流江横山段",
    }

    assessments = []
    for site_code, params in data.items():
        result = assessor.assess_site(
            site_code, site_names[site_code], params,
            target_class=QualityClass.III,
            detection_limits={
                "Hg": 0.00004, "Cd": 0.001, "As": 0.002,
                "CN": 0.004, "VPH": 0.003, "Pb": 0.01,
            }
        )
        assessments.append(result)

    print(assessor.summary_report(assessments))


def main():
    engine = get_engine("sqlite:///monitoring.db")
    init_db(engine)
    session = get_session(engine)

    print("创建监测点位...")
    sites = create_sites(session)
    print(f"  ✓ {len(sites)} 个点位")

    print("导入监测数据...")
    count = create_records(session)
    print(f"  ✓ {count} 条记录")

    session.close()

    print("\n" + "=" * 60)
    print("水质评价 (内存模式)")
    print("=" * 60)
    run_assessment()


if __name__ == "__main__":
    main()
