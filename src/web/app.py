"""
Streamlit 仪表盘 — 主入口

运行: streamlit run src/web/app.py

页面:
- 数据概览: 数据库状态、站点列表
- 数据导入: 上传 Excel → 预览 → 导入
- 水质评价: 选择断面/日期 → 评价 → 结果展示
- 报告导出: 查看已生成报告
"""

import sys
from pathlib import Path

# 确保项目根在 path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

st.set_page_config(
    page_title="玉林生态环境监测系统",
    page_icon="🌏",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 自定义样式
st.markdown("""
<style>
    .main-header { font-size: 1.8rem; font-weight: 600; color: #1F4E79; margin-bottom: 0; }
    .sub-header { font-size: 0.9rem; color: #6B7280; margin-top: 0; }
    .metric-card {
        background: #F0F7FF; border-radius: 12px; padding: 1.2rem;
        border: 1px solid #D0E4F5; text-align: center;
    }
    .metric-value { font-size: 2rem; font-weight: 600; color: #1F4E79; }
    .metric-label { font-size: 0.85rem; color: #5F7D9C; margin-top: 0.3rem; }
    .exceed-badge { background: #FDE8E8; color: #A32D2D; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }
    .pass-badge { background: #E2EFDA; color: #3B6D11; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)


def get_db_session():
    """获取数据库会话"""
    from src.database.models import get_engine, get_session
    engine = get_engine(f"sqlite:///{PROJECT_ROOT}/monitoring.db")
    return get_session(engine)


def page_overview():
    """数据概览页面"""
    st.markdown('<p class="main-header">数据概览</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">监测数据总览与站点管理</p>', unsafe_allow_html=True)

    session = get_db_session()
    try:
        from src.database.models import MonitoringSite, MonitoringRecord

        sites = session.query(MonitoringSite).all()
        records = session.query(MonitoringRecord).count()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f'<div class="metric-card"><div class="metric-value">{len(sites)}</div><div class="metric-label">监测站点</div></div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="metric-card"><div class="metric-value">{records}</div><div class="metric-label">数据记录</div></div>', unsafe_allow_html=True)
        with col3:
            exceed = session.query(MonitoringRecord).filter_by(is_exceed=True).count() if records > 0 else 0
            st.markdown(f'<div class="metric-card"><div class="metric-value">{exceed}</div><div class="metric-label">超标记录</div></div>', unsafe_allow_html=True)
        with col4:
            distinct_params = session.query(MonitoringRecord.parameter_code).distinct().count()
            st.markdown(f'<div class="metric-card"><div class="metric-value">{distinct_params}</div><div class="metric-label">监测参数</div></div>', unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("站点列表")

        if sites:
            import pandas as pd
            df = pd.DataFrame([{
                "编码": s.site_code, "名称": s.site_name,
                "要素": s.element_type, "行政区": s.district or "-",
                "流域": s.river_basin or "-", "状态": "在用" if s.is_active else "停用"
            } for s in sites])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("暂无监测站点数据，请先导入数据。")
    finally:
        session.close()


def page_import():
    """数据导入页面"""
    st.markdown('<p class="main-header">数据导入</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">上传 Excel 文件，自动导入数据库</p>', unsafe_allow_html=True)

    from src.ingestion.excel_importer import ExcelImporter

    # 要素类型选择
    element_map = {
        "地表水": "water_surface",
        "环境空气": "air_ambient",
        "土壤": "soil",
        "噪声": "noise",
    }
    element_label = st.selectbox("监测要素", list(element_map.keys()))
    element_type = element_map[element_label]

    report_no = st.text_input("报告编号", placeholder="例如: YL-202601-W")

    uploaded = st.file_uploader(
        "上传 Excel 文件",
        type=["xlsx", "xls"],
        help="支持列格式(宽表)和行格式(长表)"
    )

    if uploaded:
        # 保存临时文件
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as f:
            f.write(uploaded.read())
            tmp_path = f.name

        # 预览
        import pandas as pd
        xls = pd.ExcelFile(tmp_path)
        st.markdown("**文件预览**")
        for sheet in xls.sheet_names:
            with st.expander(f"Sheet: {sheet}"):
                df = pd.read_excel(tmp_path, sheet_name=sheet).head(10)
                st.dataframe(df, use_container_width=True)

        # 导入按钮
        if st.button("导入到数据库", type="primary"):
            db_path = str(PROJECT_ROOT / "monitoring.db")
            importer = ExcelImporter(f"sqlite:///{db_path}")
            result = importer.import_file(tmp_path, element_type=element_type, report_no=report_no or None)

            if result.success:
                st.success(f"导入完成! {result.records_imported} 条记录, {result.sites_created} 个新站点")
            else:
                st.error(f"导入出错: {'; '.join(result.errors)}")
            if result.records_skipped > 0:
                st.warning(f"跳过 {result.records_skipped} 条重复记录")
            if result.warnings:
                st.info(f"提示: {'; '.join(result.warnings)}")


def page_assessment():
    """水质评价页面"""
    st.markdown('<p class="main-header">水质评价</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">基于 GB3838-2002 的单因子评价与综合指数</p>', unsafe_allow_html=True)

    from src.database.models import MonitoringSite, MonitoringRecord
    from src.analysis.quality_assessment import WaterQualityAssessor, QualityClass
    import pandas as pd

    session = get_db_session()
    try:
        # 获取所有水站点
        sites = session.query(MonitoringSite).filter(
            MonitoringSite.element_type == "water_surface"
        ).all()

        if not sites:
            st.warning("暂无地表水站点数据，请先导入数据。")
            return

        site_options = {s.site_name: s.site_code for s in sites}
        selected_names = st.multiselect("选择断面", list(site_options.keys()))

        # 获取可用日期
        available_dates = session.query(MonitoringRecord.sample_date).filter(
            MonitoringRecord.element_type == "water_surface"
        ).distinct().order_by(MonitoringRecord.sample_date.desc()).all()
        date_options = [d[0] for d in available_dates]
        selected_date = st.selectbox("评价日期", date_options, format_func=lambda d: str(d))

        water_temp = st.number_input("水温 (°C)", value=20.0, min_value=0.0, max_value=40.0,
                                      help="用于 DO 饱和溶解氧精确计算")

        if selected_names and st.button("开始评价", type="primary"):
            assessor = WaterQualityAssessor()
            site_codes = [site_options[n] for n in selected_names]
            all_results = []

            for site_code, site_name in zip(site_codes, selected_names):
                records = session.query(MonitoringRecord).filter(
                    MonitoringRecord.site_code is not None,
                    MonitoringRecord.sample_date == selected_date,
                    MonitoringRecord.element_type == "water_surface",
                    MonitoringRecord.site.has(MonitoringSite.site_code == site_code)
                ).all()

                if not records:
                    st.info(f"{site_name}: 该日期无数据")
                    continue

                params = {r.parameter_code: r.value for r in records if r.value is not None}
                dl = {r.parameter_code: r.detection_limit for r in records if r.detection_limit}

                result = assessor.assess_site(
                    site_code, site_name, params,
                    target_class=QualityClass.III,
                    detection_limits=dl if dl else None,
                    water_temp=water_temp
                )
                all_results.append(result)

            if all_results:
                # 汇总表
                st.subheader("评价汇总")
                summary_data = []
                for a in all_results:
                    summary_data.append({
                        "断面": a.site_name,
                        "目标类别": str(a.target_class),
                        "实际类别": str(a.actual_class),
                        "综合指数": round(a.comprehensive_index, 3),
                        "参数数": a.total_params,
                        "超标数": a.exceed_params,
                        "超标率": f"{a.exceed_rate:.1f}%",
                        "首要污染物": a.primary_pollutant or "-",
                    })
                st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

                # 详细结果 - 每个断面一个 expander
                for a in all_results:
                    with st.expander(f"📊 {a.site_name} — 详细评价"):
                        detail_data = []
                        for r in a.parameter_results:
                            detail_data.append({
                                "参数": r.parameter_name,
                                "值": f"{r.value} {r.parameter_unit}",
                                "水质类别": str(r.actual_class),
                                "达标": "✅" if not r.is_exceed else "❌",
                                "超标倍数": f"{r.exceed_multiple:.2f}" if r.is_exceed else "-",
                                "单因子指数": round(r.single_factor_index, 3),
                            })
                        st.dataframe(pd.DataFrame(detail_data), use_container_width=True, hide_index=True)

                        # 污染负荷图
                        load_items = sorted(a.pollution_load_ratios.items(), key=lambda x: x[1], reverse=True)[:8]
                        if load_items:
                            import plotly.express as px
                            fig = px.bar(
                                x=[v for _, v in load_items],
                                y=[k for k, _ in load_items],
                                orientation='h',
                                title="污染负荷比 (Ki) — Top 8",
                                labels={"x": "Ki (%)", "y": ""},
                                color=[v for _, v in load_items],
                                color_continuous_scale="Reds",
                            )
                            fig.update_layout(height=300)
                            st.plotly_chart(fig, use_container_width=True)
    finally:
        session.close()


def page_reports():
    """报告页"""
    st.markdown('<p class="main-header">报告管理</p>', unsafe_allow_html=True)
    st.info("功能开发中 — 将支持一键生成 Word 评价报告")


# ======================== 主入口 ========================

PAGES = {
    "📊 数据概览": page_overview,
    "📥 数据导入": page_import,
    "🔬 水质评价": page_assessment,
    "📄 报告管理": page_reports,
}

with st.sidebar:
    st.markdown("### 🌏 玉林监测系统")
    st.caption("广西壮族自治区玉林生态环境监测中心")
    st.markdown("---")
    selected_page = st.radio("导航", list(PAGES.keys()), label_visibility="collapsed")

# 渲染选中页面
PAGES[selected_page]()
