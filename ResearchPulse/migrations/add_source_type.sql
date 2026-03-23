-- =============================================================================
-- 数据库迁移脚本：新增 source_type 字段
-- 版本: 2024.03
-- 说明: 支持多数据源报告（arxiv, hackernews, reddit, weibo, rss）
-- =============================================================================

-- 注意事项：
-- 1. 执行前请先备份数据库
-- 2. 此脚本会修改唯一索引，如果有重复数据会失败
-- 3. 执行后需要重启应用以加载新的模型定义

-- =====================================================
-- 第一步：添加 source_type 字段
-- =====================================================
ALTER TABLE daily_reports
ADD COLUMN source_type VARCHAR(20) NOT NULL DEFAULT 'arxiv'
COMMENT '数据源类型: arxiv, hackernews, reddit, weibo, rss'
AFTER report_date;

-- =====================================================
-- 第二步：添加 source_type 索引
-- =====================================================
CREATE INDEX ix_daily_reports_source_type ON daily_reports(source_type);

-- =====================================================
-- 第三步：删除旧的唯一索引
-- =====================================================
DROP INDEX ix_daily_reports_date_category ON daily_reports;

-- =====================================================
-- 第四步：创建新的联合唯一索引（日期 + 数据源 + 分类）
-- =====================================================
CREATE UNIQUE INDEX ix_daily_reports_date_source_category
ON daily_reports(report_date, source_type, category);

-- =====================================================
-- 验证迁移结果
-- =====================================================
-- 查看表结构
-- DESC daily_reports;

-- 查看索引
-- SHOW INDEX FROM daily_reports;

-- 查看已有数据
-- SELECT id, report_date, source_type, category FROM daily_reports LIMIT 10;
