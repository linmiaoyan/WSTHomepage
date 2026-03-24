"""
数据库连接和初始化
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import config

# 创建数据库引擎
engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in config.DATABASE_URL else {}
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明基类
Base = declarative_base()


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库表"""
    from app.models import Teacher, Template, Task, Questionnaire, QuestionnaireResponse, SealRequest
    from sqlalchemy import inspect, text
    
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    
    # 检查并添加缺失的列（数据库迁移）
    inspector = inspect(engine)
    
    # 检查questionnaire_responses表是否有confirmed_status列
    if 'questionnaire_responses' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('questionnaire_responses')]
        
        with engine.connect() as conn:
            # 添加confirmed_status列（如果不存在）
            if 'confirmed_status' not in columns:
                try:
                    conn.execute(text("ALTER TABLE questionnaire_responses ADD COLUMN confirmed_status VARCHAR(20) DEFAULT 'pending'"))
                    conn.commit()
                    print("已添加 confirmed_status 列")
                except Exception as e:
                    print(f"添加 confirmed_status 列时出错（可能已存在）: {e}")
            
            # 添加confirmed_at列（如果不存在）
            if 'confirmed_at' not in columns:
                try:
                    conn.execute(text("ALTER TABLE questionnaire_responses ADD COLUMN confirmed_at DATETIME"))
                    conn.commit()
                    print("已添加 confirmed_at 列")
                except Exception as e:
                    print(f"添加 confirmed_at 列时出错（可能已存在）: {e}")
    
    # 检查questionnaires表是否有share_token列
    if 'questionnaires' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('questionnaires')]
        
        with engine.connect() as conn:
            if 'share_token' not in columns:
                try:
                    conn.execute(text("ALTER TABLE questionnaires ADD COLUMN share_token VARCHAR(100)"))
                    conn.commit()
                    print("已添加 share_token 列")
                except Exception as e:
                    print(f"添加 share_token 列时出错（可能已存在）: {e}")
    
    # 检查templates表是否有placeholder_positions列
    if 'templates' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('templates')]
        
        with engine.connect() as conn:
            if 'placeholder_positions' not in columns:
                try:
                    # SQLite不支持直接添加JSON列，使用TEXT类型
                    conn.execute(text("ALTER TABLE templates ADD COLUMN placeholder_positions TEXT DEFAULT '[]'"))
                    conn.commit()
                    print("已添加 placeholder_positions 列")
                except Exception as e:
                    print(f"添加 placeholder_positions 列时出错（可能已存在）: {e}")
            else:
                # 如果列已存在，更新NULL值为空列表
                try:
                    conn.execute(text("UPDATE templates SET placeholder_positions = '[]' WHERE placeholder_positions IS NULL"))
                    conn.commit()
                    print("已更新 placeholder_positions 的NULL值")
                except Exception as e:
                    print(f"更新 placeholder_positions NULL值时出错: {e}")
    
    print("数据库初始化完成！")


if __name__ == "__main__":
    init_db()

