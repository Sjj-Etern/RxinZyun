from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# 本地流程数据（workflow_events / prescription_workflow_state）统一存 MySQL hospital 库
# （与 HIS 共享同一数据库，不再使用本地 SQLite）
MYSQL_URL = (
    f"mysql+pymysql://{settings.mysql_user}:{quote_plus(settings.mysql_pass)}"
    f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_db}?charset=utf8mb4"
)

engine = create_engine(
    MYSQL_URL,
    pool_pre_ping=True,   # 每次取连接前探活，避免 MySQL 8 小时断连
    pool_recycle=3600,    # 连接回收周期
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
