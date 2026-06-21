"""
全局配置管理

支持环境变量覆盖，便于开发/生产切换
"""

import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_DIR = DATA_DIR / "sample"

# 数据库配置
DB_URL = os.getenv("MONITORING_DB_URL", f"sqlite:///{PROJECT_ROOT}/monitoring.db")

# GG 标准限值目录
STANDARDS_DIR = PROJECT_ROOT / "standards"

# 报告输出目录
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"

# 默认评价标准
DEFAULT_STANDARDS = {
    "water_surface": "GB3838-2002",
    "water_ground": "GB/T14848-2017",
    "air_ambient": "GB3095-2012",
    "soil": "GB15618-2018",
    "noise": "GB3096-2008",
}

# 默认评价目标类别
DEFAULT_TARGET_CLASS = {
    "water_surface": "III",
    "water_ground": "III",
    "air_ambient": "II",
    "soil": "II",
    "noise": "2类",
}

# Streamlit 配置
STREAMLIT_TITLE = "玉林生态环境监测数据管理系统"
STREAMLIT_PORT = int(os.getenv("STREAMLIT_PORT", "8501"))

# 确保目录存在
for d in [DATA_DIR, SAMPLE_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)
