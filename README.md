# 玉林生态环境监测数据管理系统

> yl-monitoring-system — 面向地市级生态环境监测中心的数据管理与评价平台

## 功能概览

| 模块 | 功能 | 技术栈 |
|------|------|--------|
| 数据采集 | Excel/CSV/PDF 批量导入、手动录入 | pandas, openpyxl, xlrd |
| 数据存储 | 四要素 (水/气/土/噪声) 统一存储 | SQLAlchemy + SQLite/PostgreSQL |
| 查询统计 | 按站点/时间/参数/行政区多维查询 | pandas, Streamlit |
| 质量评价 | 单因子评价 + 综合指数评价 | GB3838/3095/3096/15618 |
| 报告生成 | Word 评价报告一键生成 | python-docx, openpyxl |
| Web 仪表盘 | 交互式数据可视化管理 | Streamlit + Plotly |

## 支持的国标

| 标准编号 | 名称 | 适用要素 |
|----------|------|----------|
| GB 3838-2002 | 地表水环境质量标准 | 地表水 (24项) |
| GB 3095-2012 | 环境空气质量标准 | 环境空气 (21项) |
| GB 3096-2008 | 声环境质量标准 | 噪声 (6类功能区) |
| GB 15618-2018 | 农用地土壤污染风险管控标准 | 土壤 (8项重金属) |

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/Surong2026/yl-monitoring-system.git
cd yl-monitoring-system

# 安装依赖
pip install -r requirements.txt

# 初始化数据库
python -c "from src.database.models import get_engine, init_db; init_db(get_engine())"

# 启动 Web 仪表盘
streamlit run src/web/app.py
```

## 项目结构

```
yl-monitoring-system/
├── src/
│   ├── database/        # 数据模型与连接管理
│   ├── ingestion/       # 数据导入与解析
│   ├── analysis/        # 统计分析 & 质量评价
│   ├── reporting/       # Word/PDF/Excel 报告生成
│   └── web/             # Streamlit 仪表盘
├── standards/           # GB 标准限值 JSON
├── tests/               # 单元测试
├── data/                # 示例数据 & 报告输出
├── docs/                # 项目文档
└── .github/workflows/   # CI/CD 流水线
```

## AI 协作工作流

本项目由 **WorkBuddy** 和 **Claude Code** 双 AI 通过 GitHub PR 协作开发：

```
WorkBuddy 开发 feature → git push → 创建 PR
    → Claude Code 审阅 diff → 提交 Review Comment
    → WorkBuddy 修正 → Claude Code 复审
    → Approved → Merge to main
    → 下一轮角色互换
```

## 许可

MIT License © 2026 广西壮族自治区玉林生态环境监测中心
