-- =============================================================================
-- ResearchPulse v2 增量迁移脚本
-- =============================================================================
-- 版本: 2025.02.18
-- 说明: 添加 arxiv_paper_type 字段，用于区分新发表论文和更新论文
-- 
-- 用法: mysql -h HOST -P PORT -u USER -pPASSWORD DB_NAME < migrate_2025.02.18.sql
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 为 articles 表添加 arxiv_paper_type 字段
-- -----------------------------------------------------------------------------
-- 说明: 该字段用于标记 arXiv 论文的类型
--   - 'new': 新发表的论文（按 submittedDate 排序获取）
--   - 'updated': 更新的论文（按 lastUpdatedDate 排序获取）
--   - '': 空值，表示旧数据或非 arXiv 文章
-- -----------------------------------------------------------------------------

-- 检查字段是否已存在（避免重复执行报错）
SET @dbname = DATABASE();
SET @tablename = 'articles';
SET @columnname = 'arxiv_paper_type';
SET @preparedStatement = (SELECT IF(
    (
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = @dbname
        AND TABLE_NAME = @tablename
        AND COLUMN_NAME = @columnname
    ) > 0,
    'SELECT 1',
    CONCAT('ALTER TABLE `', @tablename, '` ADD COLUMN `', @columnname, '` VARCHAR(20) DEFAULT \'\' COMMENT \'arXiv 论文类型: new/updated\' AFTER `arxiv_updated_time`')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- 验证字段是否添加成功
SELECT 
    COLUMN_NAME,
    COLUMN_TYPE,
    COLUMN_DEFAULT,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'articles'
    AND COLUMN_NAME = 'arxiv_paper_type';

-- 迁移完成
SELECT 'Migration completed: arxiv_paper_type column added to articles table' AS status;
