"""
Excel 数据导入引擎

支持两种常见的监测报告格式:

格式 A — 列格式 (宽表)
  每行一个断面/日期, 每列一个监测参数
  | 断面编码 | 断面名称 | 采样日期 | pH | DO | COD | NH3N | ...

格式 B — 行格式 (长表)
  每行一个参数记录
  | 断面编码 | 断面名称 | 采样日期 | 监测项目 | 单位 | 监测值 | 检出限 | ...

自动检测格式并导入到 SQLAlchemy 数据库。
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from src.database.models import (
    get_engine, get_session,
    MonitoringSite, MonitoringRecord, ElementType
)


# ======================== 参数名 → 编码映射 ========================

PARAM_NAME_TO_CODE: Dict[str, str] = {
    "pH值": "pH", "pH": "pH",
    "溶解氧": "DO", "DO": "DO",
    "化学需氧量": "COD", "化学需氧量(COD)": "COD", "COD": "COD", "CODCr": "COD",
    "高锰酸盐指数": "CODMn", "CODMn": "CODMn",
    "五日生化需氧量": "BOD5", "生化需氧量": "BOD5", "BOD5": "BOD5",
    "氨氮": "NH3N", "氨氮(NH3-N)": "NH3N", "NH3N": "NH3N", "NH3_N": "NH3N",
    "总磷": "TP", "总磷(以P计)": "TP", "TP": "TP",
    "总氮": "TN", "总氮(湖库,以N计)": "TN", "TN": "TN",
    "铜": "Cu", "Cu": "Cu",
    "锌": "Zn", "Zn": "Zn",
    "氟化物": "F", "氟化物(以F-计)": "F", "F": "F",
    "砷": "As", "As": "As",
    "汞": "Hg", "Hg": "Hg",
    "镉": "Cd", "Cd": "Cd",
    "六价铬": "Cr6", "Cr6": "Cr6",
    "铅": "Pb", "Pb": "Pb",
    "氰化物": "CN", "CN": "CN",
    "挥发酚": "VPH", "VPH": "VPH",
    "石油类": "TPH", "TPH": "TPH",
    "阴离子表面活性剂": "LAS", "阴离子": "LAS", "LAS": "LAS",
    "硫化物": "S2", "S2": "S2",
    "粪大肠菌群": "FC", "FC": "FC",
}

PARAM_UNIT_MAP: Dict[str, str] = {
    "pH": "无量纲", "DO": "mg/L", "COD": "mg/L", "CODMn": "mg/L",
    "BOD5": "mg/L", "NH3N": "mg/L", "TP": "mg/L", "TN": "mg/L",
    "Cu": "mg/L", "Zn": "mg/L", "F": "mg/L", "As": "mg/L",
    "Hg": "mg/L", "Cd": "mg/L", "Cr6": "mg/L", "Pb": "mg/L",
    "CN": "mg/L", "VPH": "mg/L", "TPH": "mg/L", "LAS": "mg/L",
    "S2": "mg/L", "FC": "个/L",
}

# 常见列名变体 (导入时会自动匹配)
COLUMN_ALIASES = {
    "site_code": ["断面编码", "站点编码", "点位编码", "site_code", "site", "code"],
    "site_name": ["断面名称", "站点名称", "点位名称", "site_name", "site name", "name"],
    "sample_date": ["采样日期", "监测日期", "日期", "date", "sample_date", "时间"],
    "parameter_name": ["监测项目", "参数名称", "项目", "参数", "指标", "parameter", "item"],
    "value": ["监测值", "测定值", "值", "value", "result"],
    "unit": ["单位", "unit"],
    "detection_limit": ["检出限", "检测限", "检出下限", "detection_limit", "DL", "MDL"],
}

ELEMENT_TYPE_COLUMNS = {
    "水": "water_surface",
    "地表水": "water_surface",
    "空气": "air_ambient",
    "环境空气": "air_ambient",
    "土壤": "soil",
    "噪声": "noise",
}


# ======================== 数据结构 ========================

@dataclass
class ImportResult:
    """导入结果"""
    file_path: str
    format_type: str  # "column" or "row"
    total_rows: int = 0
    sites_created: int = 0
    records_imported: int = 0
    records_skipped: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def __repr__(self):
        return (f"<ImportResult {self.format_type} format: "
                f"{self.records_imported} imported, "
                f"{self.records_skipped} skipped, "
                f"{len(self.errors)} errors>")


# ======================== 列名解析 ========================

def _resolve_column(col_name: str, target: str) -> bool:
    """判断列名是否匹配目标 (支持别名)"""
    cn = col_name.strip().lower()
    aliases = COLUMN_ALIASES.get(target, [])
    for alias in aliases:
        if alias.lower() in cn or cn in alias.lower():
            return True
    return False


def _find_column(df: pd.DataFrame, target: str) -> Optional[str]:
    """在 DataFrame 中查找匹配的列名"""
    for col in df.columns:
        if _resolve_column(str(col), target):
            return col
    return None


def _normalize_param_name(name: str) -> str:
    """标准化参数名为编码 (大小写不敏感)"""
    s = str(name).strip()
    # 精确匹配
    if s in PARAM_NAME_TO_CODE:
        return PARAM_NAME_TO_CODE[s]
    # 小写匹配
    s_lower = s.lower()
    for k, v in PARAM_NAME_TO_CODE.items():
        if k.lower() == s_lower:
            return v
    # 去括号后匹配
    clean = re.sub(r'[（(][^)）]*[)）]', '', s).strip()
    if clean in PARAM_NAME_TO_CODE:
        return PARAM_NAME_TO_CODE[clean]
    # 去括号后小写匹配
    clean_lower = clean.lower()
    for k, v in PARAM_NAME_TO_CODE.items():
        if k.lower() == clean_lower:
            return v
    # 如果本身已经是标准编码
    return s


# ======================== 数值解析 ========================

# 非数值标记模式
_ND_PATTERN = re.compile(
    r'^(?:ND|nd|N\.?D\.?|未检出|未检出|低于检出限|低于检测限'
    r'|<检出限|<检测限|—|--|/|\\|-|LOD)$'
)
_QUALIFIED_PATTERN = re.compile(r'^[<>≤≥]?\s*(-?\d+\.?\d*)\s*L?\s*$')

def _parse_value(raw) -> Optional[float]:
    """
    解析监测值, 兼容中国监测报告常见格式。

    返回 float 或 None (无法解析/未检出)
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        if pd.isna(raw):
            return None
        return float(raw)

    s = str(raw).strip()

    # 空值
    if not s or s == 'nan':
        return None

    # ND / 未检出 标记
    if _ND_PATTERN.match(s):
        return None

    # <0.01 / >100 / ≤0.05 / 0.025L 等
    m = _QUALIFIED_PATTERN.match(s)
    if m:
        return float(m.group(1))

    # 尝试直接转换
    try:
        return float(s)
    except ValueError:
        return None


# ======================== 格式检测 ========================

def detect_format(df: pd.DataFrame) -> str:
    """
    检测 Excel 格式类型。

    Returns:
        "column": 列格式 (每个参数一列)
        "row": 行格式 (每行一个参数)
    """
    col_names = [str(c).lower() for c in df.columns]

    # 行格式检测: 有"监测项目"、"参数名称"等列
    row_indicators = ["监测项目", "参数名称", "项目", "指标", "parameter"]
    for ind in row_indicators:
        if any(ind in c for c in col_names):
            return "row"

    # 列格式检测: 多个参数列 (pH, DO, COD 等)
    param_count = 0
    for c in col_names:
        normalized = _normalize_param_name(str(c))
        if normalized in PARAM_NAME_TO_CODE:
            param_count += 1
    if param_count >= 2:
        return "column"

    # 默认尝试列格式
    return "column"


# ======================== 导入引擎 ========================

class ExcelImporter:
    """Excel 数据导入器"""

    def __init__(self, db_url: str = "sqlite:///monitoring.db"):
        self.engine = get_engine(db_url)
        self.element_type = "water_surface"

    def set_element_type(self, element_type: str):
        """设置监测要素类型"""
        if element_type in ELEMENT_TYPE_COLUMNS:
            self.element_type = ELEMENT_TYPE_COLUMNS[element_type]
        elif element_type in [e.value for e in ElementType]:
            self.element_type = element_type
        else:
            raise ValueError(f"不支持的要素类型: {element_type}")

    def import_file(self, filepath: str, element_type: str = "water_surface",
                    report_no: Optional[str] = None,
                    skip_duplicates: bool = True) -> ImportResult:
        """
        导入单个 Excel 文件。

        Args:
            filepath: Excel 文件路径
            element_type: 监测要素 (地表水/空气/土壤/噪声)
            report_no: 报告编号 (不提供则从文件名推断)
            skip_duplicates: 是否跳过重复记录 (同站点+日期+参数)

        Returns:
            ImportResult
        """
        self.set_element_type(element_type)

        result = ImportResult(file_path=filepath, format_type="unknown")
        if report_no is None:
            result.warnings.append("未提供报告编号, 从文件名推断")

        try:
            # 读取所有 sheet
            xls = pd.ExcelFile(filepath)
            for sheet_name in xls.sheet_names:
                try:
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                except Exception as e:
                    result.errors.append(f"Sheet '{sheet_name}' 读取失败: {e}")
                    continue
                if df.empty:
                    continue
                sheet_result = self._import_dataframe(df, sheet_name, report_no, skip_duplicates)
                result.sites_created += sheet_result.sites_created
                result.records_imported += sheet_result.records_imported
                result.records_skipped += sheet_result.records_skipped
                result.errors.extend(sheet_result.errors)
                if not result.format_type or result.format_type == "unknown":
                    result.format_type = sheet_result.format_type
        except Exception as e:
            result.errors.append(f"读取文件失败: {e}")

        result.total_rows = result.records_imported + result.records_skipped
        return result

    def _import_dataframe(self, df: pd.DataFrame, sheet_name: str,
                          report_no: Optional[str], skip_duplicates: bool) -> ImportResult:
        """导入单个 DataFrame"""
        result = ImportResult(file_path=sheet_name, format_type="unknown")

        # 清理列名
        df.columns = [str(c).strip() for c in df.columns]

        # 移除全空行
        df = df.dropna(how="all")

        # 检测格式
        fmt = detect_format(df)
        result.format_type = fmt

        if fmt == "column":
            self._import_column_format(df, result, report_no, skip_duplicates)
        else:
            self._import_row_format(df, result, report_no, skip_duplicates)

        return result

    # -------- 列格式导入 --------

    def _import_column_format(self, df: pd.DataFrame, result: ImportResult,
                               report_no: Optional[str], skip_duplicates: bool):
        """处理列格式 (宽表): 每行一个断面, 每列一个参数"""
        # 定位关键列
        site_code_col = _find_column(df, "site_code")
        site_name_col = _find_column(df, "site_name")
        date_col = _find_column(df, "sample_date")

        # 找出所有参数列 (非关键列的数值列)
        key_cols = set()
        for col_name in [site_code_col, site_name_col, date_col]:
            if col_name:
                key_cols.add(col_name)

        param_cols = [c for c in df.columns if c not in key_cols]
        # 进一步过滤: 只保留能映射到标准参数的列
        param_cols = [c for c in param_cols if _normalize_param_name(c) in PARAM_NAME_TO_CODE
                      or _normalize_param_name(c) in PARAM_UNIT_MAP]

        if not param_cols:
            result.errors.append(f"列格式未识别到参数列 (sheet: {sheet_name})")
            return

        session = get_session(self.engine)
        try:
            for _, row in df.iterrows():
                site_code = str(row[site_code_col]) if site_code_col in df.columns else None
                site_name = str(row[site_name_col]) if site_name_col in df.columns else (site_code or "未命名")
                sample_date = self._parse_date(row[date_col]) if date_col in df.columns else date.today()

                if site_code is None or pd.isna(site_code):
                    continue

                # 确保站点存在
                site = self._get_or_create_site(session, str(site_code), str(site_name), result)

                for param_col in param_cols:
                    raw_value = row[param_col]
                    if pd.isna(raw_value):
                        continue

                    value = _parse_value(raw_value)
                    if value is None:
                        continue  # ND/未检出, 不导入

                    param_code = _normalize_param_name(param_col)
                    self._insert_record(session, site, sample_date, param_code,
                                        value, report_no, skip_duplicates, result)

            session.commit()
        except Exception as e:
            session.rollback()
            result.errors.append(f"导入异常: {e}")
        finally:
            session.close()

    # -------- 行格式导入 --------

    def _import_row_format(self, df: pd.DataFrame, result: ImportResult,
                            report_no: Optional[str], skip_duplicates: bool):
        """处理行格式 (长表): 每行一个参数"""
        site_code_col = _find_column(df, "site_code")
        site_name_col = _find_column(df, "site_name")
        date_col = _find_column(df, "sample_date")
        param_col = _find_column(df, "parameter_name")
        value_col = _find_column(df, "value")
        unit_col = _find_column(df, "unit")
        dl_col = _find_column(df, "detection_limit")

        if param_col is None:
            result.errors.append("行格式缺少'监测项目'列")
            return
        if value_col is None:
            result.errors.append("行格式缺少'监测值'列")
            return

        session = get_session(self.engine)
        try:
            for _, row in df.iterrows():
                # 跳过可能的表头行
                param_name = str(row[param_col])
                if param_name in ["监测项目", "参数名称", "项目"]:
                    continue

                site_code = str(row[site_code_col]) if site_code_col and not pd.isna(row[site_code_col]) else None
                if site_code is None or site_code == "nan":
                    continue

                site_name = str(row[site_name_col]) if site_name_col and not pd.isna(row[site_name_col]) else site_code
                sample_date = self._parse_date(row[date_col]) if date_col else date.today()
                raw_value = row[value_col]
                if pd.isna(raw_value):
                    continue

                value = _parse_value(raw_value)
                if value is None:
                    continue  # ND/未检出, 不导入

                param_code = _normalize_param_name(param_name)
                site = self._get_or_create_site(session, site_code, site_name, result)
                self._insert_record(session, site, sample_date, param_code,
                                    value, report_no, skip_duplicates, result)

            session.commit()
        except Exception as e:
            session.rollback()
            result.errors.append(f"导入异常: {e}")
        finally:
            session.close()

    # -------- 辅助方法 --------

    def _parse_date(self, value: Any) -> date:
        """解析日期"""
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if pd.isna(value):
            return date.today()
        return pd.Timestamp(value).date()

    def _get_or_create_site(self, session, site_code: str, site_name: str,
                            result: ImportResult) -> MonitoringSite:
        """查找或创建站点"""
        site = session.query(MonitoringSite).filter_by(site_code=site_code).first()
        if site is None:
            site = MonitoringSite(
                site_code=site_code,
                site_name=site_name,
                element_type=self.element_type,
            )
            session.add(site)
            session.flush()
            result.sites_created += 1
        return site

    def _insert_record(self, session, site: MonitoringSite, sample_date: date,
                       param_code: str, value: float, report_no: Optional[str],
                       skip_duplicates: bool, result: ImportResult):
        """插入单条记录"""
        if skip_duplicates:
            existing = session.query(MonitoringRecord).filter_by(
                site_id=site.id, sample_date=sample_date,
                parameter_code=param_code, report_no=report_no
            ).first()
            if existing:
                result.records_skipped += 1
                return

        unit = PARAM_UNIT_MAP.get(param_code, "")
        param_name = param_code  # 后续可从标准库查中文名

        record = MonitoringRecord(
            site_id=site.id,
            sample_date=sample_date,
            element_type=self.element_type,
            parameter_code=param_code,
            parameter_name=param_name,
            parameter_unit=unit,
            value=float(value),
            standard_code="GB3838-2002" if self.element_type == "water_surface" else None,
            report_no=report_no,
        )
        session.add(record)
        result.records_imported += 1
