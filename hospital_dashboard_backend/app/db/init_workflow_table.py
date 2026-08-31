"""
数据库表初始化脚本
创建 prescription_workflow_state / workflow_events 表（MySQL hospital 库）
"""
from app.db.models import Base
from app.db.session import engine

# 创建所有表（幂等：已存在则跳过）
Base.metadata.create_all(bind=engine)

print("✅ 数据库表创建完成（MySQL hospital 库）")
print("   - prescription_workflow_state 表已就绪")
print("   - workflow_events 表已就绪")
