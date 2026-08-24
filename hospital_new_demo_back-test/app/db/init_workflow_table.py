"""
数据库表初始化脚本
创建 prescription_workflow_state 表
"""
from sqlalchemy import create_engine
from app.db.models import Base
from app.core.config import settings

# 创建数据库引擎（使用本地 SQLite）
engine = create_engine(settings.database_url, echo=True)

# 创建所有表
Base.metadata.create_all(bind=engine)

print("✅ 数据库表创建完成")
print("   - prescription_workflow_state 表已创建")
