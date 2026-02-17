-- =============================================================================
-- ResearchPulse 新数据源迁移脚本
-- 用途: 添加 HackerNews、Reddit、Twitter 数据源表
-- 执行: mysql -h HOST -u USER -p DB_NAME < add_new_sources.sql
-- =============================================================================

SET NAMES utf8mb4;

-- -----------------------------------------------------------------------------
-- hackernews_sources 表 - HackerNews 板块配置
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `hackernews_sources` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `feed_type` VARCHAR(50) NOT NULL COMMENT '板块类型: front, new, best, ask, show',
  `feed_name` VARCHAR(100) NOT NULL COMMENT '板块显示名称',
  `description` TEXT DEFAULT NULL COMMENT '板块描述',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `last_fetched_at` DATETIME DEFAULT NULL COMMENT '最后抓取时间',
  `error_count` INT NOT NULL DEFAULT 0 COMMENT '连续错误次数',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `feed_type` (`feed_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='HackerNews 板块配置表';

-- -----------------------------------------------------------------------------
-- reddit_sources 表 - Reddit 订阅源配置
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `reddit_sources` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `source_type` VARCHAR(50) NOT NULL COMMENT '源类型: subreddit, user',
  `source_name` VARCHAR(100) NOT NULL COMMENT 'Subreddit 名或用户名',
  `display_name` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '显示名称',
  `description` TEXT DEFAULT NULL COMMENT '描述',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `last_fetched_at` DATETIME DEFAULT NULL COMMENT '最后抓取时间',
  `error_count` INT NOT NULL DEFAULT 0 COMMENT '连续错误次数',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_reddit_source_unique` (`source_type`, `source_name`),
  KEY `idx_reddit_sources_type` (`source_type`),
  KEY `idx_reddit_sources_name` (`source_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Reddit 订阅源配置表';

-- -----------------------------------------------------------------------------
-- twitter_sources 表 - Twitter 用户订阅配置
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `twitter_sources` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `username` VARCHAR(100) NOT NULL COMMENT 'Twitter 用户名(不含@)',
  `display_name` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '显示名称',
  `description` TEXT DEFAULT NULL COMMENT '描述',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `last_fetched_at` DATETIME DEFAULT NULL COMMENT '最后抓取时间',
  `error_count` INT NOT NULL DEFAULT 0 COMMENT '连续错误次数',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Twitter 用户订阅配置表';

-- -----------------------------------------------------------------------------
-- 初始数据 - HackerNews 板块
-- -----------------------------------------------------------------------------
INSERT IGNORE INTO `hackernews_sources` (`feed_type`, `feed_name`, `description`, `is_active`) VALUES
('front', 'Top Stories', 'Hacker News 首页热门故事', 1),
('new', 'New Stories', 'Hacker News 最新提交的故事', 0),
('best', 'Best Stories', 'Hacker News 历史最佳故事', 0),
('ask', 'Ask HN', 'Hacker News 问答讨论', 0),
('show', 'Show HN', 'Hacker News 项目展示', 0);

-- -----------------------------------------------------------------------------
-- 初始数据 - Reddit 订阅源 (示例，默认禁用)
-- -----------------------------------------------------------------------------
INSERT IGNORE INTO `reddit_sources` (`source_type`, `source_name`, `display_name`, `description`, `is_active`) VALUES
('subreddit', 'MachineLearning', 'Machine Learning', '机器学习研究与讨论', 0),
('subreddit', 'artificial', 'Artificial Intelligence', '人工智能综合讨论', 0),
('subreddit', 'deeplearning', 'Deep Learning', '深度学习讨论', 0);

-- Done
SELECT 'Migration completed successfully!' AS status;
