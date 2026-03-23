# =============================================================================
# 迁移脚本：新增 source_type 字段
# =============================================================================
#
# 执行方式:
#   方式1: 直接在 MySQL 中执行 SQL
#   方式2: 通过 Python 脚本执行迁移
#
# 注意事项:
#   1. 执行前请先备份数据库
#   2. 此脚本会修改唯一索引，如果有重复数据会失败
#   3. 执行后需要重启应用以加载新的模型定义
#
# =============================================================================

MIGRATION_SQL = """
-- 新增 source_type 字段
ALTER TABLE daily_reports 
ADD COLUMN source_type VARCHAR(20) NOT NULL DEFAULT 'arxiv' 
COMMENT '数据源类型: arxiv, hackernews, reddit, weibo, rss' 
AFTER report_date;

-- 添加 source_type 索引
CREATE INDEX ix_daily_reports_source_type ON daily_reports(source_type);

-- 删除旧的唯一索引
DROP INDEX ix_daily_reports_date_category ON daily_reports;

-- 创建新的联合唯一索引（日期 + 数据源 + 分类）
CREATE UNIQUE INDEX ix_daily_reports_date_source_category 
ON daily_reports(report_date, source_type, category);
"""


def run_migration(connection):
    """执行迁移脚本
    
    Args:
        connection: 数据库连接对象
    """
    cursor = connection.cursor()
    
    try:
        # 检查 source_type 列是否已存在
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'daily_reports' 
            AND COLUMN_NAME = 'source_type'
        """)
        
        if cursor.fetchone()[0] > 0:
            print("Migration already applied: source_type column exists")
            return
        
        # 检查旧索引是否存在
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.STATISTICS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'daily_reports' 
            AND INDEX_NAME = 'ix_daily_reports_date_category'
        """)
        
        old_index_exists = cursor.fetchone()[0] > 0
        
        # 添加 source_type 列
        print("Adding source_type column...")
        cursor.execute("""
            ALTER TABLE daily_reports 
            ADD COLUMN source_type VARCHAR(20) NOT NULL DEFAULT 'arxiv' 
            COMMENT '数据源类型: arxiv, hackernews, reddit, weibo, rss' 
            AFTER report_date
        """)
        
        # 添加 source_type 索引
        print("Adding source_type index...")
        cursor.execute("""
            CREATE INDEX ix_daily_reports_source_type 
            ON daily_reports(source_type)
        """)
        
        # 删除旧索引（如果存在）
        if old_index_exists:
            print("Dropping old unique index...")
            cursor.execute("DROP INDEX ix_daily_reports_date_category ON daily_reports")
        
        # 创建新的联合唯一索引
        print("Creating new unique index...")
        cursor.execute("""
            CREATE UNIQUE INDEX ix_daily_reports_date_source_category 
            ON daily_reports(report_date, source_type, category)
        """)
        
        connection.commit()
        print("Migration completed successfully!")
        
    except Exception as e:
        connection.rollback()
        print(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    import pymysql
    import os
    
    # 从环境变量获取数据库配置
    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 3306)),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "researchpulse"),
        "charset": "utf8mb4",
    }
    
    print("Connecting to database...")
    connection = pymysql.connect(**db_config)
    
    try:
        run_migration(connection)
    finally:
        connection.close()
