"""
生态环境监测数据管理系统 — SQLAlchemy 数据模型

覆盖四要素：地表水、环境空气、土壤、噪声
支持 GB3838-2002 / GB3095-2012 / GB3096-2008 / GB15618-2018 标准评价
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime,
    Boolean, Text, ForeignKey, Index, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import enum

Base = declarative_base()


# ======================== 枚举类型 ========================

class ElementType(str, enum.Enum):
    """监测要素类型"""
    WATER_SURFACE = "water_surface"       # 地表水
    WATER_GROUND = "water_ground"         # 地下水
    AIR_AMBIENT = "air_ambient"           # 环境空气
    SOIL = "soil"                         # 土壤
    NOISE = "noise"                       # 噪声


# ======================== 核心表 ========================

class MonitoringSite(Base):
    """监测点位信息"""
    __tablename__ = "monitoring_sites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    site_code = Column(String(50), unique=True, nullable=False, index=True, comment="点位编码")
    site_name = Column(String(200), nullable=False, comment="点位名称")
    element_type = Column(String(30), nullable=False, index=True, comment="要素类型")
    longitude = Column(Float, comment="经度 (WGS84)")
    latitude = Column(Float, comment="纬度 (WGS84)")
    district = Column(String(100), index=True, comment="行政区 (县/区)")
    address = Column(String(500), comment="详细地址")
    river_basin = Column(String(100), comment="所属流域")
    water_body = Column(String(200), comment="所属水体")
    section_type = Column(String(50), comment="断面类型: 国控/省控/市控")
    noise_zone = Column(String(10), comment="噪声功能区类别")
    is_active = Column(Boolean, default=True, comment="是否在用")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    records = relationship("MonitoringRecord", back_populates="site", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Site {self.site_code}: {self.site_name}>"


class MonitoringRecord(Base):
    """监测数据记录 (四要素通用结构)"""
    __tablename__ = "monitoring_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(Integer, ForeignKey("monitoring_sites.id", ondelete="CASCADE"),
                     nullable=False, index=True, comment="关联点位")
    sample_date = Column(Date, nullable=False, index=True, comment="采样日期")
    element_type = Column(String(30), nullable=False, index=True, comment="要素类型")
    parameter_code = Column(String(50), nullable=False, index=True, comment="监测项目编码")
    parameter_name = Column(String(100), nullable=False, comment="监测项目名称")
    parameter_unit = Column(String(20), comment="单位 (mg/L, ug/m3, dB(A) 等)")
    value = Column(Float, nullable=False, comment="监测值")
    detection_limit = Column(Float, comment="检出限")
    is_detected = Column(Boolean, default=True, comment="是否检出")
    analysis_method = Column(String(200), comment="分析方法")
    standard_code = Column(String(50), comment="执行标准")
    quality_class = Column(String(10), comment="水质类别/空气质量级别")
    is_exceed = Column(Boolean, default=False, index=True, comment="是否超标")
    exceed_multiple = Column(Float, comment="超标倍数")
    report_no = Column(String(100), index=True, comment="报告编号")
    remarks = Column(Text, comment="备注")
    created_at = Column(DateTime, default=datetime.utcnow)

    site = relationship("MonitoringSite", back_populates="records")

    __table_args__ = (
        Index("idx_record_query", "element_type", "parameter_code", "sample_date"),
    )

    def __repr__(self):
        return f"<Record {self.parameter_name}={self.value}{self.parameter_unit} @ {self.sample_date}>"


class QualityStandard(Base):
    """环境质量标准限值"""
    __tablename__ = "quality_standards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    standard_code = Column(String(50), nullable=False, index=True, comment="标准编号")
    element_type = Column(String(30), nullable=False, comment="适用要素")
    parameter_code = Column(String(50), nullable=False, index=True, comment="项目编码")
    parameter_name = Column(String(100), nullable=False, comment="项目名称")
    parameter_unit = Column(String(20), comment="单位")
    class_level = Column(String(10), nullable=False, comment="类别/级别")
    limit_value = Column(Float, nullable=False, comment="标准限值")
    operator = Column(String(5), default="<=", comment="比较运算符")
    remarks = Column(Text, comment="备注")
    version_year = Column(Integer, comment="标准发布年份")

    __table_args__ = (
        Index("idx_standard_lookup", "standard_code", "class_level", "parameter_code"),
    )

    def __repr__(self):
        return f"<Standard {self.standard_code} {self.parameter_name} {self.class_level}: {self.operator}{self.limit_value}>"


class AssessmentResult(Base):
    """评价结果"""
    __tablename__ = "assessment_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    record_id = Column(Integer, ForeignKey("monitoring_records.id", ondelete="CASCADE"),
                       nullable=False, index=True, comment="关联监测记录")
    target_class = Column(String(10), nullable=False, comment="评价目标类别")
    standard_code = Column(String(50), nullable=False, comment="评价标准")
    is_exceed = Column(Boolean, default=False, comment="是否超标")
    exceed_multiple = Column(Float, default=0.0, comment="超标倍数")
    single_factor_index = Column(Float, comment="单因子指数")
    comprehensive_index = Column(Float, comment="综合污染指数")
    assessment_date = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Assessment record#{self.record_id} exceed={self.is_exceed}>"


class Report(Base):
    """评价报告元数据"""
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String(50), nullable=False, comment="类型: monthly/quarterly/annual/special")
    title = Column(String(300), nullable=False, comment="报告标题")
    element_type = Column(String(30), comment="涉及要素")
    period_start = Column(Date, nullable=False, comment="统计起始")
    period_end = Column(Date, nullable=False, comment="统计截止")
    site_count = Column(Integer, comment="涉及点位数量")
    record_count = Column(Integer, comment="涉及数据条数")
    exceed_summary = Column(Text, comment="超标摘要")
    file_path = Column(String(500), comment="文件路径")
    file_format = Column(String(20), comment="文件格式: docx/pdf/xlsx")
    created_by = Column(String(100), comment="生成人/工具")
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Report {self.report_type}: {self.title}>"


# ======================== 数据库工具 ========================

def get_engine(db_url: str = "sqlite:///monitoring.db"):
    """创建数据库引擎"""
    return create_engine(db_url, echo=False)


def init_db(engine):
    """初始化所有表"""
    Base.metadata.create_all(engine)


def get_session(engine):
    """获取会话"""
    Session = sessionmaker(bind=engine)
    return Session()
