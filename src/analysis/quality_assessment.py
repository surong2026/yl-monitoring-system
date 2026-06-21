"""
水质评价引擎 — GB3838-2002 地表水环境质量标准

实现两种评价方法:
1. 单因子评价法 (Single Factor Assessment)
   - 确定单项水质类别 (I~V, 劣V)
   - 断面总体类别取各参数最差类别
   - 超标判断与超标倍数计算

2. 综合污染指数法 (Comprehensive Pollution Index)
   - 单因子污染指数 Pi = Ci / Si
   - 综合污染指数 P = ΣPi / n
   - 污染负荷比 Ki = Pi / ΣPi × 100%

特殊参数处理:
- pH: 范围限值 (6-9), 需双向判断
- DO: 下限值 (≥), 浓度越低越差
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd


# ======================== 数据结构 ========================

class QualityClass(Enum):
    """水质类别"""
    I = 1
    II = 2
    III = 3
    IV = 4
    V = 5
    INFERIOR_V = 6  # 劣V类

    def __str__(self):
        return "劣V" if self == QualityClass.INFERIOR_V else f"{self.name}类"

    @classmethod
    def from_value(cls, v):
        """从字符串或数字解析"""
        if v == "劣V" or v == "INFERIOR_V":
            return cls.INFERIOR_V
        for m in cls:
            if m.name == v or m.value == v:
                return m
        raise ValueError(f"未知水质类别: {v}")


@dataclass
class ParameterResult:
    """单项参数评价结果"""
    parameter_code: str
    parameter_name: str
    parameter_unit: str
    value: float
    target_class: QualityClass
    actual_class: QualityClass
    is_exceed: bool
    exceed_multiple: float
    single_factor_index: float  # Pi
    limit_value: float  # 目标类别限值
    detection_limit: Optional[float] = None
    is_detected: bool = True

    def __repr__(self):
        flag = "超标" if self.is_exceed else "达标"
        return (f"<{self.parameter_name} {self.value}{self.parameter_unit} "
                f"({self.actual_class}, {flag}, Pi={self.single_factor_index:.2f})>")


@dataclass
class SiteAssessment:
    """断面综合评价结果"""
    site_code: str
    site_name: str
    target_class: QualityClass
    actual_class: QualityClass
    parameter_results: List[ParameterResult] = field(default_factory=list)

    # 综合指数
    comprehensive_index: float = 0.0         # P
    pollution_load_ratios: Dict[str, float] = field(default_factory=dict)  # Ki

    # 统计
    total_params: int = 0
    exceed_params: int = 0
    exceed_rate: float = 0.0  # 超标率 (%)

    primary_pollutant: Optional[str] = None   # 首要污染物

    def __repr__(self):
        return (f"<{self.site_name} {self.target_class}→{self.actual_class} "
                f"P={self.comprehensive_index:.2f} "
                f"超标{self.exceed_params}/{self.total_params}>")


# ======================== 标准限值加载 ========================

class StandardLoader:
    """加载 GB3838-2002 标准限值"""

    STANDARD_FILE = Path(__file__).resolve().parent.parent.parent / "standards" / "GB3838-2002.json"

    # 按水质类别排序 (从好到差)
    CLASS_ORDER = ["I", "II", "III", "IV", "V"]

    def __init__(self, filepath: Optional[Path] = None):
        self.filepath = filepath or self.STANDARD_FILE
        self._standards: Dict[str, dict] = {}  # param_code -> {class: limit}
        self._load()

    def _load(self):
        """从 JSON 加载标准限值 (支持 class_I / I 两种键名)"""
        with open(self.filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        for p in data["parameters"]:
            code = p["code"]
            self._standards[code] = {
                "name": p["name"],
                "unit": p.get("unit", ""),
                "operator": p.get("operator", "<="),
            }
            for cls_name in self.CLASS_ORDER:
                # 兼容 class_I 和 I 两种键名
                json_key = f"class_{cls_name}"
                if json_key in p:
                    self._standards[code][cls_name] = p[json_key]
                elif cls_name in p:
                    self._standards[code][cls_name] = p[cls_name]

    def get_limit(self, param_code: str, class_level: str) -> Optional[float]:
        """获取指定参数在指定类别的限值"""
        return self._standards.get(param_code, {}).get(class_level)

    def get_unit(self, param_code: str) -> str:
        return self._standards.get(param_code, {}).get("unit", "")

    @property
    def parameters(self) -> List[str]:
        return list(self._standards.keys())


# ======================== 参数比较逻辑 ========================

def _get_operator(param_code: str, loader: StandardLoader) -> str:
    """获取参数在标准中的比较运算符"""
    info = loader._standards.get(param_code, {})
    return info.get("operator", "<=")

def _is_range_type(value) -> bool:
    """判断限值是否为范围型 (数组)"""
    return isinstance(value, (list, tuple))


# ======================== 评价核心算法 ========================

class WaterQualityAssessor:
    """地表水水质评价"""

    def __init__(self, standard_file: Optional[Path] = None):
        self.loader = StandardLoader(standard_file)

    # -------- 单因子评价 --------

    def classify_parameter(self, param_code: str, value: float) -> QualityClass:
        """
        判定单个参数的水质类别。

        - 常规参数 (<=): 值越小越好, ≤限值即为该类
        - 下限参数 (>=): 值越大越好, ≥限值即为该类 (如 DO)
        - 范围型: 在 [min, max] 内即为该类 (如 pH)
        """
        operator = _get_operator(param_code, self.loader)

        # 范围型 (如 pH: [6, 9])
        if operator == "range":
            for cls_name in self.loader.CLASS_ORDER:
                limit = self.loader.get_limit(param_code, cls_name)
                if limit is not None and _is_range_type(limit):
                    min_v, max_v = limit[0], limit[1]
                    if min_v <= value <= max_v:
                        return QualityClass.from_value(cls_name)
            return QualityClass.INFERIOR_V

        # 下限型 (如 DO: >= 5.0)
        if operator == ">=":
            for cls_name in self.loader.CLASS_ORDER:  # I → V
                limit = self.loader.get_limit(param_code, cls_name)
                if limit is not None and value >= limit:
                    return QualityClass.from_value(cls_name)
            return QualityClass.INFERIOR_V  # 低于V类限值

        # 常规上限型 (<=)
        for cls_name in self.loader.CLASS_ORDER:
            limit = self.loader.get_limit(param_code, cls_name)
            if limit is not None and value <= limit:
                return QualityClass.from_value(cls_name)

        return QualityClass.INFERIOR_V

    def check_exceed(self, param_code: str, value: float,
                     target_class: QualityClass = QualityClass.III) -> Tuple[bool, float]:
        """
        检查是否超过目标类别限值, 并计算超标倍数。

        Returns:
            (是否超标, 超标倍数)
        """
        operator = _get_operator(param_code, self.loader)

        # 范围型 (如 pH)
        if operator == "range":
            limit = self.loader.get_limit(param_code, target_class.name)
            if limit is not None and _is_range_type(limit):
                min_v, max_v = limit[0], limit[1]
                if value < min_v:
                    return True, (min_v - value) / min_v if min_v > 0 else 0
                elif value > max_v:
                    return True, (value - max_v) / max_v if max_v > 0 else 0
                return False, 0.0
            return False, 0.0

        # 下限型 (如 DO)
        if operator == ">=":
            limit = self.loader.get_limit(param_code, target_class.name)
            if limit is None:
                return False, 0.0
            if value < limit:
                return True, (limit - value) / limit if limit > 0 else 0
            return False, 0.0

        # 常规上限型 (<=)
        limit = self.loader.get_limit(param_code, target_class.name)
        if limit is None:
            return False, 0.0
        if value > limit:
            return True, (value - limit) / limit if limit > 0 else 0
        return False, 0.0

    def single_factor_index(self, param_code: str, value: float,
                            target_class: QualityClass = QualityClass.III) -> float:
        """
        计算单因子污染指数 Pi

        - 常规参数 (<=): Pi = value / limit
        - 范围型 (如 pH): Pi = |value - 7| / |boundary - 7|
        - 下限型 (如 DO): Pi = |DO_f - value| / |DO_f - limit|
          (DO_f = 468/(31.6+T), 简化取常温饱和值 8.0)
        """
        operator = _get_operator(param_code, self.loader)

        # 范围型 (pH)
        if operator == "range":
            limit = self.loader.get_limit(param_code, target_class.name)
            if limit is not None and _is_range_type(limit):
                min_v, max_v = limit[0], limit[1]
                if value > 7:
                    return (value - 7) / (max_v - 7) if max_v != 7 else 0.0
                elif value < 7:
                    return (7 - value) / (7 - min_v) if min_v != 7 else 0.0
                return 0.0
            return 0.0

        # 下限型 (DO)
        if operator == ">=":
            DO_SAT = 8.0  # 常温饱和溶解氧
            limit = self.loader.get_limit(param_code, target_class.name)
            if limit is None:
                return 0.0
            if value <= 0:
                return limit if limit > 0 else 10.0
            if value >= DO_SAT:
                return 0.0
            if value >= limit:
                denom = DO_SAT - limit
                if denom <= 0:
                    denom = 1.0
                return (DO_SAT - value) / denom
            # 超标: Pi = 1 + (limit - value) / limit
            return 1.0 + (limit - value) / limit if limit > 0 else 1.0

        # 常规上限型 (<=)
        limit = self.loader.get_limit(param_code, target_class.name)
        if limit is None or limit == 0:
            return 0.0
        return value / limit

    # -------- 批量评价 --------

    def assess_site(self, site_code: str, site_name: str,
                    parameters: Dict[str, float],
                    target_class: QualityClass = QualityClass.III,
                    detection_limits: Optional[Dict[str, float]] = None) -> SiteAssessment:
        """
        评价单个断面的水质。

        Args:
            site_code: 断面编码
            site_name: 断面名称
            parameters: {param_code: value} 各参数监测值
            target_class: 目标水质类别 (默认 III 类)
            detection_limits: {param_code: limit} 检出限 (低于检出限的值取 1/2 检出限参与评价)

        Returns:
            SiteAssessment 包含完整的评价结果
        """
        if detection_limits is None:
            detection_limits = {}

        results: List[ParameterResult] = []
        actual_class = QualityClass.I  # 初始为最好, 后续取最差

        for param_code, value in parameters.items():
            # 检出限处理
            dl = detection_limits.get(param_code)
            is_detected = True
            eval_value = value
            if dl is not None and value < dl:
                is_detected = False
                eval_value = dl / 2.0  # 按检出限一半参与评价

            # 分类
            param_class = self.classify_parameter(param_code, eval_value)

            # 超标判断
            is_exceed, exceed_multiple = self.check_exceed(param_code, eval_value, target_class)

            # 单因子指数
            si = self.single_factor_index(param_code, eval_value, target_class)

            results.append(ParameterResult(
                parameter_code=param_code,
                parameter_name=self.loader._standards.get(param_code, {}).get("name", param_code),
                parameter_unit=self.loader.get_unit(param_code),
                value=value,
                target_class=target_class,
                actual_class=param_class,
                is_exceed=is_exceed,
                exceed_multiple=exceed_multiple,
                single_factor_index=si,
                limit_value=self.loader.get_limit(param_code, target_class.name) or 0,
                detection_limit=dl,
                is_detected=is_detected,
            ))

            # 更新最差类别
            if param_class.value > actual_class.value:
                actual_class = param_class

        # 综合指数
        all_pi = [r.single_factor_index for r in results]
        total_pi = sum(all_pi)
        n = len(all_pi)
        comprehensive_index = total_pi / n if n > 0 else 0.0

        # 污染负荷比
        load_ratios = {r.parameter_name: (r.single_factor_index / total_pi * 100) if total_pi > 0 else 0.0
                       for r in results}

        # 首要污染物 = 污染负荷比最大且超标的参数
        exceed_results = [r for r in results if r.is_exceed]
        primary = max(exceed_results, key=lambda r: r.single_factor_index).parameter_name if exceed_results else None

        # 统计
        exceed_count = sum(1 for r in results if r.is_exceed)

        return SiteAssessment(
            site_code=site_code,
            site_name=site_name,
            target_class=target_class,
            actual_class=actual_class,
            parameter_results=results,
            comprehensive_index=comprehensive_index,
            pollution_load_ratios=load_ratios,
            total_params=len(results),
            exceed_params=exceed_count,
            exceed_rate=(exceed_count / len(results) * 100) if results else 0.0,
            primary_pollutant=primary,
        )

    def assess_dataframe(self, df: pd.DataFrame,
                         site_col: str = "site_code",
                         param_col: str = "parameter_code",
                         value_col: str = "value",
                         target_class: QualityClass = QualityClass.III) -> List[SiteAssessment]:
        """
        从 DataFrame 批量评价多个断面。

        期望列: site_code, parameter_code, value, site_name(可选), detection_limit(可选)
        """
        grouped = df.groupby(site_col)
        assessments = []

        for site_code, group in grouped:
            params = dict(zip(group[param_col], group[value_col]))
            site_name = group.get("site_name", [site_code]).iloc[0] if "site_name" in group.columns else site_code
            dl_dict = {}
            if "detection_limit" in group.columns:
                dl_dict = dict(zip(group[param_col], group["detection_limit"]))

            assessment = self.assess_site(
                site_code, str(site_name), params,
                target_class=target_class, detection_limits=dl_dict
            )
            assessments.append(assessment)

        return assessments

    def to_dataframe(self, assessment: SiteAssessment) -> pd.DataFrame:
        """将评价结果转为 DataFrame"""
        rows = []
        for r in assessment.parameter_results:
            rows.append({
                "断面编码": assessment.site_code,
                "断面名称": assessment.site_name,
                "目标类别": str(assessment.target_class),
                "实际类别": str(assessment.actual_class),
                "综合指数": round(assessment.comprehensive_index, 3),
                "参数代码": r.parameter_code,
                "参数名称": r.parameter_name,
                "单位": r.parameter_unit,
                "监测值": r.value,
                "水质类别": str(r.actual_class),
                "是否超标": "是" if r.is_exceed else "否",
                "超标倍数": r.exceed_multiple,
                "单因子指数": round(r.single_factor_index, 3),
                "标准限值": r.limit_value,
            })
        return pd.DataFrame(rows)

    def summary_report(self, assessments: List[SiteAssessment]) -> str:
        """生成文字评价摘要"""
        lines = []
        lines.append("=" * 60)
        lines.append("玉林市地表水水质评价报告 (GB3838-2002)")
        lines.append("=" * 60)

        for a in assessments:
            lines.append(f"\n【{a.site_code}】{a.site_name}")
            lines.append(f"  目标类别: {a.target_class}  实际类别: {a.actual_class}")
            lines.append(f"  综合污染指数 P = {a.comprehensive_index:.3f}")
            lines.append(f"  监测参数: {a.total_params}项  超标: {a.exceed_params}项 ({a.exceed_rate:.1f}%)")

            if a.primary_pollutant:
                lines.append(f"  首要污染物: {a.primary_pollutant}")

            lines.append(f"  单项评价:")
            for r in a.parameter_results:
                flag = "超标" if r.is_exceed else "达标"
                dl_note = f"(未检出, 取1/2检出限)" if not r.is_detected else ""
                lines.append(f"    {r.parameter_name}: {r.value}{r.parameter_unit} "
                             f"[{r.actual_class}] {flag} Pi={r.single_factor_index:.3f} {dl_note}")

            # 污染负荷排名
            sorted_load = sorted(a.pollution_load_ratios.items(),
                                 key=lambda x: x[1], reverse=True)
            lines.append(f"  污染负荷比 (Ki):")
            for name, ki in sorted_load:
                bar = "█" * int(ki / 2)
                lines.append(f"    {name}: {ki:.1f}% {bar}")

        return "\n".join(lines)
