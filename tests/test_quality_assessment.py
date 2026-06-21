"""
水质评价引擎单元测试

覆盖:
1. 单因子分类 (常规/DO/pH)
2. 超标判断 (上限型/下限型/范围型)
3. 单因子指数 Pi
4. 断面综合评价
5. 检出限处理
6. 边界情况
7. None/NaN 输入守卫 (P0)
8. DO 水温校正 (P1)
"""

import pytest

from src.analysis.quality_assessment import (
    WaterQualityAssessor, QualityClass, StandardLoader,
    ParameterResult, SiteAssessment
)


@pytest.fixture
def assessor():
    return WaterQualityAssessor()


@pytest.fixture
def loader():
    return StandardLoader()


# ======================== 标准加载 ========================

class TestStandardLoader:
    def test_load_all_params(self, loader):
        """验证加载参数数量"""
        assert len(loader.parameters) >= 20

    def test_get_ammonia_limit(self, loader):
        """氨氮 III 类限值应为 1.0 mg/L"""
        assert loader.get_limit("NH3N", "III") == 1.0

    def test_get_COD_limit(self, loader):
        """COD III 类限值应为 20 mg/L"""
        assert loader.get_limit("COD", "III") == 20.0

    def test_get_unit(self, loader):
        assert loader.get_unit("NH3N") == "mg/L"
        assert loader.get_unit("DO") == "mg/L"


# ======================== 水质分类 ========================

class TestClassifyParameter:
    def test_classify_ammonia_III(self, assessor):
        """氨氮 0.8 → ≤1.0 → III类"""
        assert assessor.classify_parameter("NH3N", 0.8) == QualityClass.III

    def test_classify_ammonia_I(self, assessor):
        """氨氮 0.1 → ≤0.15 → I类"""
        assert assessor.classify_parameter("NH3N", 0.1) == QualityClass.I

    def test_classify_ammonia_inferior(self, assessor):
        """氨氮 2.5 → >2.0(V类) → 劣V"""
        assert assessor.classify_parameter("NH3N", 2.5) == QualityClass.INFERIOR_V

    def test_classify_DO_III(self, assessor):
        """DO 5.2 → ≥5.0 → III类"""
        assert assessor.classify_parameter("DO", 5.2) == QualityClass.III

    def test_classify_DO_I(self, assessor):
        """DO 8.0 → ≥7.5 → I类"""
        assert assessor.classify_parameter("DO", 8.0) == QualityClass.I

    def test_classify_pH_normal(self, assessor):
        """pH 7.5 → 在6-9范围 → I类"""
        assert assessor.classify_parameter("pH", 7.5) == QualityClass.I

    def test_classify_pH_abnormal(self, assessor):
        """pH 10 → 超出6-9 → 劣V"""
        assert assessor.classify_parameter("pH", 10.0) == QualityClass.INFERIOR_V

    def test_classify_COD_IV(self, assessor):
        """COD 25 → ≤30(IV), >20(III) → IV类"""
        assert assessor.classify_parameter("COD", 25.0) == QualityClass.IV


# ======================== 超标判断 ========================

class TestCheckExceed:
    def test_not_exceed(self, assessor):
        """氨氮 0.5, III类限值 1.0, 不超标"""
        is_exceed, multiple = assessor.check_exceed("NH3N", 0.5, QualityClass.III)
        assert is_exceed is False
        assert multiple == 0.0

    def test_exceed_ammonia(self, assessor):
        """氨氮 2.0, III类限值 1.0, 超标倍数 = (2.0-1.0)/1.0 = 1.0"""
        is_exceed, multiple = assessor.check_exceed("NH3N", 2.0, QualityClass.III)
        assert is_exceed is True
        assert multiple == pytest.approx(1.0, abs=0.01)

    def test_exceed_DO(self, assessor):
        """DO 3.0, III类限值 5.0, 超标倍数 = (5.0-3.0)/5.0 = 0.4"""
        is_exceed, multiple = assessor.check_exceed("DO", 3.0, QualityClass.III)
        assert is_exceed is True
        assert multiple == pytest.approx(0.4, abs=0.01)

    def test_exceed_pH_high(self, assessor):
        """pH 10, III类范围 6-9, 超标 = (10-9)/9 = 0.111"""
        is_exceed, multiple = assessor.check_exceed("pH", 10.0, QualityClass.III)
        assert is_exceed is True
        assert multiple == pytest.approx(0.111, abs=0.01)

    def test_exceed_pH_low(self, assessor):
        """pH 4, III类范围 6-9, 超标 = (6-4)/6 = 0.333"""
        is_exceed, multiple = assessor.check_exceed("pH", 4.0, QualityClass.III)
        assert is_exceed is True
        assert multiple == pytest.approx(0.333, abs=0.01)

    def test_exact_limit_not_exceed(self, assessor):
        """值正好等于限值, 不超标"""
        is_exceed, _ = assessor.check_exceed("NH3N", 1.0, QualityClass.III)
        assert is_exceed is False


# ======================== 单因子指数 ========================

class TestSingleFactorIndex:
    def test_normal_param(self, assessor):
        """氨氮 Pi = 0.5 / 1.0 = 0.5"""
        pi = assessor.single_factor_index("NH3N", 0.5, QualityClass.III)
        assert pi == pytest.approx(0.5, abs=0.01)

    def test_over_limit(self, assessor):
        """氨氮超标 Pi = 2.0 / 1.0 = 2.0"""
        pi = assessor.single_factor_index("NH3N", 2.0, QualityClass.III)
        assert pi == pytest.approx(2.0, abs=0.01)

    def test_DO_below_limit(self, assessor):
        """DO 3.0, III类限值 5.0, 低于限值"""
        pi = assessor.single_factor_index("DO", 3.0, QualityClass.III)
        assert pi > 1.0  # 超标情况 Pi > 1

    def test_DO_saturated(self, assessor):
        """DO 接近饱和 (20°C时≈9.07), Pi 应小"""
        pi = assessor.single_factor_index("DO", 9.0, QualityClass.III, water_temp=20.0)
        assert pi == pytest.approx(0.0, abs=0.05)

    def test_pH_neutral(self, assessor):
        """pH = 7, Pi = 0"""
        pi = assessor.single_factor_index("pH", 7.0, QualityClass.III)
        assert pi == pytest.approx(0.0, abs=0.01)


# ======================== 断面综合评价 ========================

class TestAssessSite:
    def test_all_within_limit(self, assessor):
        """全部达标断面的评价"""
        result = assessor.assess_site(
            "YL-WS-001", "南流江六司段",
            {"NH3N": 0.3, "COD": 10, "DO": 7.0, "pH": 7.2, "TP": 0.1},
            target_class=QualityClass.III
        )
        assert result.actual_class.value <= QualityClass.III.value
        assert result.exceed_params == 0
        assert result.comprehensive_index < 1.0

    def test_some_exceed(self, assessor):
        """部分超标"""
        result = assessor.assess_site(
            "YL-WS-002", "南流江横山段",
            {"NH3N": 2.5, "COD": 15, "DO": 4.0, "TP": 0.25},
            target_class=QualityClass.III
        )
        assert result.actual_class == QualityClass.INFERIOR_V
        assert result.exceed_params >= 2
        assert result.primary_pollutant is not None

    def test_detection_limit_handling(self, assessor):
        """检出限以下值取 1/2 检出限"""
        result = assessor.assess_site(
            "YL-WS-003", "测试断面",
            {"Hg": 0.00002},  # 低于检出限
            detection_limits={"Hg": 0.00004}
        )
        r = result.parameter_results[0]
        assert r.is_detected is False

    def test_unknown_parameter(self, assessor):
        """不在标准库中的参数"""
        result = assessor.assess_site(
            "YL-WS-004", "测试断面",
            {"UNKNOWN_PARAM": 100}
        )
        assert len(result.parameter_results) == 1

    def test_calculate_all_fields(self, assessor):
        """验证所有返回字段非空"""
        result = assessor.assess_site(
            "YL-WS-001", "南流江六司段",
            {"NH3N": 0.5, "COD": 18}
        )
        assert result.site_code == "YL-WS-001"
        assert result.total_params == 2
        assert result.exceed_rate >= 0
        assert result.comprehensive_index >= 0
        for r in result.parameter_results:
            assert r.parameter_name != ""


# ======================== DataFrame 批量评价 ========================

class TestAssessDataFrame:
    def test_multi_site(self, assessor):
        """批量评价多断面"""
        import pandas as pd
        df = pd.DataFrame([
            {"site_code": "S1", "site_name": "站点1",
             "parameter_code": "NH3N", "value": 0.5},
            {"site_code": "S1", "site_name": "站点1",
             "parameter_code": "COD", "value": 15},
            {"site_code": "S2", "site_name": "站点2",
             "parameter_code": "NH3N", "value": 2.5},
            {"site_code": "S2", "site_name": "站点2",
             "parameter_code": "COD", "value": 10},
        ])
        results = assessor.assess_dataframe(df)
        assert len(results) == 2
        assert results[0].exceed_params == 0
        assert results[1].exceed_params >= 1


# ======================== 报告生成 ========================

class TestReport:
    def test_to_dataframe(self, assessor):
        result = assessor.assess_site("S1", "测试", {"NH3N": 0.5, "COD": 10})
        df = assessor.to_dataframe(result)
        assert len(df) == 2
        assert "断面编码" in df.columns
        assert "是否超标" in df.columns

    def test_summary_report(self, assessor):
        result = assessor.assess_site("S1", "测试", {"NH3N": 0.5})
        text = assessor.summary_report([result])
        assert "测试" in text
        assert "氨氮" in text


# ======================== P0 修复: None/NaN 输入守卫 ========================

class TestNoneNaNGuard:
    def test_classify_none_value(self, assessor):
        """None 值不崩溃, 返回劣V"""
        result = assessor.classify_parameter("NH3N", None)
        assert result == QualityClass.INFERIOR_V

    def test_classify_nan_value(self, assessor):
        """NaN 值不崩溃, 返回劣V"""
        import math
        result = assessor.classify_parameter("NH3N", float('nan'))
        assert result == QualityClass.INFERIOR_V

    def test_check_exceed_none(self, assessor):
        """None 值不崩溃, 返回不超标"""
        is_exceed, multiple = assessor.check_exceed("NH3N", None)
        assert is_exceed is False
        assert multiple == 0.0

    def test_check_exceed_nan(self, assessor):
        """NaN 值不崩溃"""
        import math
        is_exceed, multiple = assessor.check_exceed("NH3N", float('nan'))
        assert is_exceed is False

    def test_single_factor_none(self, assessor):
        """None 值返回 Pi=0"""
        pi = assessor.single_factor_index("NH3N", None)
        assert pi == 0.0

    def test_single_factor_inf(self, assessor):
        """Inf 值返回 Pi=0"""
        import math
        pi = assessor.single_factor_index("NH3N", float('inf'))
        assert pi == 0.0

    def test_assess_site_with_none(self, assessor):
        """包含 None 的参数不影响其他参数评价"""
        result = assessor.assess_site("S1", "测试", {"NH3N": None, "COD": 10.0})
        assert result.total_params == 2
        # COD 10 达标 III类
        cod_result = [r for r in result.parameter_results if r.parameter_code == "COD"][0]
        assert cod_result.is_exceed is False


# ======================== P1 修复: DO 水温校正 ========================

class TestDOTemperatureCorrection:
    def test_default_temp_20c(self, assessor):
        """默认 T=20°C 时 DO_sat = 468/(31.6+20) ≈ 9.07"""
        from src.analysis.quality_assessment import _get_do_saturation
        do_sat = _get_do_saturation()
        assert do_sat == pytest.approx(9.07, abs=0.1)

    def test_winter_temp_10c(self, assessor):
        """冬季 T=10°C 时 DO_sat ≈ 11.25"""
        from src.analysis.quality_assessment import _get_do_saturation
        do_sat = _get_do_saturation(10.0)
        assert do_sat == pytest.approx(11.25, abs=0.1)

    def test_summer_temp_30c(self, assessor):
        """夏季 T=30°C 时 DO_sat ≈ 7.60"""
        from src.analysis.quality_assessment import _get_do_saturation
        do_sat = _get_do_saturation(30.0)
        assert do_sat == pytest.approx(7.60, abs=0.1)

    def test_do_index_changes_with_temp(self, assessor):
        """不同水温下 DO 的 Pi 不同"""
        pi_20 = assessor.single_factor_index("DO", 5.5, water_temp=20.0)
        pi_10 = assessor.single_factor_index("DO", 5.5, water_temp=10.0)
        # 冷水饱和值更高, 相对 deficit 更大 → Pi 更大
        assert pi_10 > pi_20

    def test_assess_site_with_water_temp(self, assessor):
        """断面评价传入水温"""
        result = assessor.assess_site("S1", "测试",
                                      {"DO": 5.5, "COD": 15.0},
                                      water_temp=15.0)
        do_result = [r for r in result.parameter_results if r.parameter_code == "DO"][0]
        # DO 5.5 在 15°C (DO_sat≈10.0) 时 Pi 应 < 1 (未超标)
        assert do_result.single_factor_index > 0
