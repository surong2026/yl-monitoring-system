"""
数据导入模块单元测试

覆盖:
1. 格式检测 (列格式 vs 行格式)
2. 参数名标准化
3. 列格式导入
4. 行格式导入
5. 重复数据跳过
6. 异常处理
"""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.ingestion.excel_importer import (
    ExcelImporter, ImportResult, detect_format,
    _normalize_param_name, _resolve_column, _find_column,
    PARAM_NAME_TO_CODE
)
from src.database.models import get_engine, init_db


@pytest.fixture
def importer():
    """创建内存数据库导入器"""
    imp = ExcelImporter("sqlite:///:memory:")
    init_db(imp.engine)
    return imp


@pytest.fixture
def column_df():
    """列格式 DataFrame"""
    return pd.DataFrame([
        {"断面编码": "YL-WS-001", "断面名称": "六司段", "采样日期": "2026-01-15",
         "pH": 7.3, "DO": 7.1, "COD": 12.0, "NH3N": 0.35, "TP": 0.08},
        {"断面编码": "YL-WS-002", "断面名称": "横山段", "采样日期": "2026-01-15",
         "pH": 7.1, "DO": 4.2, "COD": 18.0, "NH3N": 2.1, "TP": 0.32},
    ])


@pytest.fixture
def row_df():
    """行格式 DataFrame"""
    return pd.DataFrame([
        {"断面编码": "YL-WS-001", "断面名称": "六司段", "采样日期": "2026-01-15",
         "监测项目": "pH", "单位": "无量纲", "监测值": 7.3},
        {"断面编码": "YL-WS-001", "断面名称": "六司段", "采样日期": "2026-01-15",
         "监测项目": "溶解氧", "单位": "mg/L", "监测值": 7.1},
        {"断面编码": "YL-WS-001", "断面名称": "六司段", "采样日期": "2026-01-15",
         "监测项目": "化学需氧量", "单位": "mg/L", "监测值": 12.0},
        {"断面编码": "YL-WS-001", "断面名称": "六司段", "采样日期": "2026-01-15",
         "监测项目": "氨氮", "单位": "mg/L", "监测值": 0.35},
    ])


# ======================== 格式检测 ========================

class TestDetectFormat:
    def test_detect_column_format(self, column_df):
        assert detect_format(column_df) == "column"

    def test_detect_row_format(self, row_df):
        assert detect_format(row_df) == "row"


# ======================== 参数名标准化 ========================

class TestNormalizeParamName:
    def test_direct_match(self):
        assert _normalize_param_name("pH") == "pH"
        assert _normalize_param_name("DO") == "DO"
        assert _normalize_param_name("COD") == "COD"

    def test_chinese_to_code(self):
        assert _normalize_param_name("氨氮") == "NH3N"
        assert _normalize_param_name("溶解氧") == "DO"
        assert _normalize_param_name("化学需氧量") == "COD"
        assert _normalize_param_name("总磷") == "TP"

    def test_chinese_with_parens(self):
        assert _normalize_param_name("氨氮(NH3-N)") == "NH3N"
        assert _normalize_param_name("氟化物(以F-计)") == "F"


# ======================== 列名解析 ========================

class TestResolveColumn:
    def test_resolve_exact(self):
        assert _resolve_column("断面编码", "site_code") is True
        assert _resolve_column("site_code", "site_code") is True

    def test_resolve_alias(self):
        assert _resolve_column("站点编码", "site_code") is True
        assert _resolve_column("采样日期", "sample_date") is True

    def test_find_column(self):
        df = pd.DataFrame(columns=["站点编码", "站点名称", "采样日期", "pH"])
        assert _find_column(df, "site_code") == "站点编码"
        assert _find_column(df, "sample_date") == "采样日期"


# ======================== 列格式导入 ========================

class TestColumnFormatImport:
    def test_import_basic(self, importer):
        df = pd.DataFrame([
            {"断面编码": "S1", "断面名称": "测试站", "采样日期": "2026-01-15",
             "pH": 7.3, "DO": 7.1, "COD": 12.0, "NH3N": 0.35},
        ])
        result = ImportResult(file_path="", format_type="")
        importer._import_column_format(df, result, "REP-001", skip_duplicates=True)
        assert result.records_imported == 4
        assert result.sites_created == 1
        assert len(result.errors) == 0

    def test_import_multiple_sites(self, importer):
        df = pd.DataFrame([
            {"断面编码": "S1", "断面名称": "A站", "采样日期": "2026-01-15",
             "pH": 7.3, "DO": 7.1, "COD": 12.0},
            {"断面编码": "S2", "断面名称": "B站", "采样日期": "2026-01-15",
             "pH": 7.1, "DO": 4.2, "COD": 18.0},
        ])
        result = ImportResult(file_path="", format_type="")
        importer._import_column_format(df, result, "REP-001", skip_duplicates=True)
        assert result.records_imported == 6
        assert result.sites_created == 2

    def test_skip_duplicates(self, importer):
        """重复导入同站点同日期同参数应跳过"""
        df = pd.DataFrame([
            {"断面编码": "S1", "断面名称": "测试", "采样日期": "2026-01-15",
             "pH": 7.3, "DO": 7.1},
        ])
        result = ImportResult(file_path="", format_type="")
        importer._import_column_format(df, result, "REP-001", skip_duplicates=True)
        assert result.records_imported == 2

        # 再次导入
        result2 = ImportResult(file_path="", format_type="")
        importer._import_column_format(df, result2, "REP-001", skip_duplicates=True)
        assert result2.records_skipped == 2
        assert result2.records_imported == 0

    def test_do_not_skip(self, importer):
        """不跳过重复时允许重复导入"""
        df = pd.DataFrame([
            {"断面编码": "S1", "断面名称": "测试", "采样日期": "2026-01-15",
             "pH": 7.3},
        ])
        result = ImportResult(file_path="", format_type="")
        importer._import_column_format(df, result, "REP-001", skip_duplicates=True)
        result2 = ImportResult(file_path="", format_type="")
        importer._import_column_format(df, result2, "REP-001", skip_duplicates=False)
        assert result2.records_imported == 1
        assert result2.records_skipped == 0

    def test_alias_columns(self, importer):
        """别名列名识别"""
        df = pd.DataFrame([
            {"站点编码": "S1", "站点名称": "测试", "日期": "2026-01-15",
             "pH": 7.3, "DO": 7.1},
        ])
        result = ImportResult(file_path="", format_type="")
        importer._import_column_format(df, result, "REP-001", skip_duplicates=True)
        assert result.records_imported == 2


# ======================== 行格式导入 ========================

class TestRowFormatImport:
    def test_import_basic(self, importer):
        df = pd.DataFrame([
            {"断面编码": "S1", "断面名称": "测试", "采样日期": "2026-01-15",
             "监测项目": "pH", "监测值": 7.3},
            {"断面编码": "S1", "断面名称": "测试", "采样日期": "2026-01-15",
             "监测项目": "氨氮", "监测值": 0.35},
        ])
        result = ImportResult(file_path="", format_type="")
        importer._import_row_format(df, result, "REP-001", skip_duplicates=True)
        assert result.records_imported == 2
        assert len(result.errors) == 0

    def test_chinese_param_names(self, importer):
        """中文参数名自动映射为编码"""
        df = pd.DataFrame([
            {"断面编码": "S1", "断面名称": "测试", "采样日期": "2026-01-15",
             "监测项目": "溶解氧", "监测值": 7.1},
            {"断面编码": "S1", "断面名称": "测试", "采样日期": "2026-01-15",
             "监测项目": "化学需氧量", "监测值": 12.0},
        ])
        result = ImportResult(file_path="", format_type="")
        importer._import_row_format(df, result, "REP-001", skip_duplicates=True)
        assert result.records_imported == 2


# ======================== Excel 文件导入 ========================

class TestExcelFileImport:
    def test_import_column_xlsx(self, importer):
        """测试导入列格式 xlsx 文件"""
        df = pd.DataFrame([
            {"断面编码": "S1", "断面名称": "测试", "采样日期": "2026-01-15",
             "pH": 7.3, "COD": 12.0},
        ])
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            df.to_excel(f.name, index=False)
            result = importer.import_file(f.name, element_type="水",
                                          report_no="TEST-001")
        assert result.records_imported == 2
        assert result.format_type == "column"

    def test_import_row_xlsx(self, importer):
        """测试导入行格式 xlsx 文件"""
        df = pd.DataFrame([
            {"断面编码": "S1", "断面名称": "测试", "采样日期": "2026-01-15",
             "监测项目": "pH", "监测值": 7.3},
        ])
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            df.to_excel(f.name, index=False)
            result = importer.import_file(f.name, element_type="水",
                                          report_no="TEST-002")
        assert result.records_imported == 1
        assert result.format_type == "row"
