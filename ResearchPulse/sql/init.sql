-- =============================================================================
-- ResearchPulse v2 数据库初始化脚本
-- =============================================================================
-- 用法: mysql -h HOST -P PORT -u USER -pPASSWORD DB_NAME < init.sql
-- 
-- 注意事项:
--   1. 所有 ID 字段使用 BIGINT 类型，确保数据量增长时不会溢出
--   2. 外键约束使用 ON DELETE CASCADE 或 ON DELETE SET NULL
--   3. 字符集: utf8mb4_unicode_ci
--   4. superuser 配置通过环境变量或 .env 文件设置
-- =============================================================================

-- 设置字符集和外键检查
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- =============================================================================
-- 表结构定义
-- =============================================================================

-- -----------------------------------------------------------------------------
-- users 表 - 用户账户
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `username` VARCHAR(50) NOT NULL COMMENT '用户名',
  `email` VARCHAR(100) NOT NULL COMMENT '邮箱地址',
  `password_hash` VARCHAR(255) NOT NULL COMMENT '密码哈希值',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `is_superuser` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否超级管理员',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `last_login_at` DATETIME DEFAULT NULL COMMENT '最后登录时间',
  `email_notifications_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用邮件通知',
  `email_digest_frequency` VARCHAR(20) NOT NULL DEFAULT 'daily' COMMENT '邮件摘要频率: daily, weekly, none',
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`),
  KEY `idx_users_username` (`username`),
  KEY `idx_users_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- -----------------------------------------------------------------------------
-- roles 表 - 角色
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `roles`;
CREATE TABLE `roles` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(50) NOT NULL COMMENT '角色名称',
  `description` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '角色描述',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `idx_roles_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色表';

-- -----------------------------------------------------------------------------
-- permissions 表 - 权限
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `permissions`;
CREATE TABLE `permissions` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL COMMENT '权限名称 (格式: 资源:操作)',
  `resource` VARCHAR(50) NOT NULL COMMENT '资源名称',
  `action` VARCHAR(50) NOT NULL COMMENT '操作类型',
  `description` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '权限描述',
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `idx_permissions_name` (`name`),
  KEY `idx_permissions_resource` (`resource`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='权限表';

-- -----------------------------------------------------------------------------
-- user_roles 表 - 用户角色关联
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `user_roles`;
CREATE TABLE `user_roles` (
  `user_id` BIGINT NOT NULL COMMENT '用户ID',
  `role_id` BIGINT NOT NULL COMMENT '角色ID',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`user_id`, `role_id`),
  KEY `idx_user_roles_role_id` (`role_id`),
  CONSTRAINT `user_roles_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `user_roles_ibfk_2` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户角色关联表';

-- -----------------------------------------------------------------------------
-- role_permissions 表 - 角色权限关联
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `role_permissions`;
CREATE TABLE `role_permissions` (
  `role_id` BIGINT NOT NULL COMMENT '角色ID',
  `permission_id` BIGINT NOT NULL COMMENT '权限ID',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`role_id`, `permission_id`),
  KEY `idx_role_permissions_permission_id` (`permission_id`),
  CONSTRAINT `role_permissions_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE,
  CONSTRAINT `role_permissions_ibfk_2` FOREIGN KEY (`permission_id`) REFERENCES `permissions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色权限关联表';

-- -----------------------------------------------------------------------------
-- articles 表 - 文章 (核心表)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `articles`;
CREATE TABLE `articles` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `source_type` VARCHAR(20) NOT NULL COMMENT '来源类型: arxiv, rss, wechat, weibo, hackernews, reddit, twitter',
  `source_id` VARCHAR(100) NOT NULL COMMENT '来源ID',
  `external_id` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '外部ID',
  `title` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '标题',
  `url` VARCHAR(2000) NOT NULL DEFAULT '' COMMENT 'URL',
  `author` VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '作者',
  `summary` TEXT NOT NULL COMMENT '摘要',
  `content` TEXT NOT NULL COMMENT '内容',
  `cover_image_url` VARCHAR(2000) NOT NULL DEFAULT '' COMMENT '封面图片URL',
  `category` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '分类',
  `tags` JSON DEFAULT NULL COMMENT '标签JSON数组',
  `publish_time` DATETIME DEFAULT NULL COMMENT '发布时间',
  `crawl_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '爬取时间',
  `is_archived` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否归档',
  `archived_at` DATETIME DEFAULT NULL COMMENT '归档时间',
  -- arXiv 专用字段
  `arxiv_id` VARCHAR(50) DEFAULT NULL COMMENT 'arXiv ID',
  `arxiv_primary_category` VARCHAR(200) DEFAULT NULL COMMENT 'arXiv 主分类',
  `arxiv_comment` TEXT DEFAULT NULL COMMENT 'arXiv 注释',
  `arxiv_updated_time` DATETIME DEFAULT NULL COMMENT 'arXiv 更新时间',
  -- 微信专用字段
  `wechat_account_name` VARCHAR(200) DEFAULT NULL COMMENT '微信公众号名称',
  `wechat_digest` TEXT DEFAULT NULL COMMENT '微信摘要',
  -- AI 处理结果字段
  `content_summary` TEXT DEFAULT NULL COMMENT 'AI摘要或翻译',
  `ai_summary` TEXT DEFAULT NULL COMMENT 'AI中文摘要',
  `ai_category` VARCHAR(50) DEFAULT NULL COMMENT 'AI分类',
  `importance_score` INT DEFAULT NULL COMMENT '重要性评分 (1-10)',
  `one_liner` VARCHAR(500) DEFAULT NULL COMMENT '一句话结论',
  `key_points` JSON DEFAULT NULL COMMENT '关键要点JSON',
  `impact_assessment` JSON DEFAULT NULL COMMENT '影响评估JSON',
  `actionable_items` JSON DEFAULT NULL COMMENT '可执行项JSON',
  `ai_processed_at` DATETIME DEFAULT NULL COMMENT 'AI处理时间',
  `ai_provider` VARCHAR(50) DEFAULT NULL COMMENT 'AI提供商',
  `ai_model` VARCHAR(100) DEFAULT NULL COMMENT 'AI模型',
  `token_used` INT DEFAULT NULL COMMENT 'Token消耗',
  `processing_method` VARCHAR(20) DEFAULT NULL COMMENT '处理方法: ai, rule, cached, screen',
  -- 社交指标
  `read_count` INT NOT NULL DEFAULT 0 COMMENT '阅读数',
  `like_count` INT NOT NULL DEFAULT 0 COMMENT '点赞数',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_articles_source_external` (`source_type`, `source_id`, `external_id`),
  KEY `ix_articles_publish_time` (`publish_time`),
  KEY `ix_articles_crawl_time` (`crawl_time`),
  KEY `ix_articles_archived` (`is_archived`),
  KEY `ix_articles_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文章表';

-- -----------------------------------------------------------------------------
-- user_article_states 表 - 用户文章状态
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `user_article_states`;
CREATE TABLE `user_article_states` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` BIGINT NOT NULL COMMENT '用户ID',
  `article_id` BIGINT NOT NULL COMMENT '文章ID',
  `is_read` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已读',
  `is_starred` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否收藏',
  `read_at` DATETIME DEFAULT NULL COMMENT '阅读时间',
  `starred_at` DATETIME DEFAULT NULL COMMENT '收藏时间',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_article` (`user_id`, `article_id`),
  KEY `idx_user_article_states_article_id` (`article_id`),
  CONSTRAINT `user_article_states_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `user_article_states_ibfk_2` FOREIGN KEY (`article_id`) REFERENCES `articles` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户文章状态表';

-- -----------------------------------------------------------------------------
-- action_items 表 - 行动项
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `action_items`;
CREATE TABLE `action_items` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `article_id` BIGINT NOT NULL COMMENT '文章ID',
  `user_id` BIGINT NOT NULL COMMENT '用户ID',
  `type` VARCHAR(50) NOT NULL COMMENT '类型: 跟进, 验证, 决策, 触发器',
  `description` TEXT NOT NULL COMMENT '描述',
  `priority` VARCHAR(10) NOT NULL COMMENT '优先级: 高, 中, 低',
  `status` VARCHAR(20) NOT NULL COMMENT '状态: pending, completed, dismissed',
  `completed_at` DATETIME DEFAULT NULL COMMENT '完成时间',
  `dismissed_at` DATETIME DEFAULT NULL COMMENT '忽略时间',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_action_items_user_status` (`user_id`, `status`),
  KEY `ix_action_items_status` (`status`),
  KEY `ix_action_items_user_id` (`user_id`),
  KEY `ix_action_items_article_id` (`article_id`),
  CONSTRAINT `action_items_ibfk_1` FOREIGN KEY (`article_id`) REFERENCES `articles` (`id`) ON DELETE CASCADE,
  CONSTRAINT `action_items_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='行动项表';

-- -----------------------------------------------------------------------------
-- ai_processing_logs 表 - AI处理日志
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `ai_processing_logs`;
CREATE TABLE `ai_processing_logs` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `article_id` BIGINT NOT NULL COMMENT '文章ID',
  `provider` VARCHAR(50) NOT NULL COMMENT 'AI提供商',
  `model` VARCHAR(100) NOT NULL COMMENT '模型名称',
  `task_type` VARCHAR(50) NOT NULL COMMENT '任务类型: content_high, content_low, paper_full, screen',
  `input_chars` INT NOT NULL DEFAULT 0 COMMENT '输入字符数',
  `output_chars` INT NOT NULL DEFAULT 0 COMMENT '输出字符数',
  `duration_ms` INT NOT NULL DEFAULT 0 COMMENT '处理耗时(毫秒)',
  `success` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否成功',
  `error_message` TEXT DEFAULT NULL COMMENT '错误信息',
  `cached` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否缓存命中',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_ai_processing_logs_article_id` (`article_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI处理日志表';

-- -----------------------------------------------------------------------------
-- article_embeddings 表 - 文章嵌入向量元数据
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `article_embeddings`;
CREATE TABLE `article_embeddings` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `article_id` BIGINT NOT NULL COMMENT '文章ID',
  `milvus_id` VARCHAR(100) DEFAULT NULL COMMENT 'Milvus主键',
  `provider` VARCHAR(50) NOT NULL COMMENT '嵌入提供商',
  `model_name` VARCHAR(100) NOT NULL COMMENT '模型名称',
  `dimension` INT NOT NULL COMMENT '向量维度',
  `computed_at` DATETIME NOT NULL COMMENT '计算时间',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_article_embeddings_article_id` (`article_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文章嵌入向量元数据表';

-- -----------------------------------------------------------------------------
-- article_topics 表 - 文章话题关联
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `article_topics`;
CREATE TABLE `article_topics` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `article_id` BIGINT NOT NULL COMMENT '文章ID',
  `topic_id` BIGINT NOT NULL COMMENT '话题ID',
  `match_score` FLOAT NOT NULL DEFAULT 0 COMMENT '匹配分数',
  `matched_keywords` JSON DEFAULT NULL COMMENT '匹配的关键词',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_article_topic` (`article_id`, `topic_id`),
  KEY `ix_article_topics_article_id` (`article_id`),
  KEY `ix_article_topics_topic_id` (`topic_id`),
  CONSTRAINT `article_topics_ibfk_1` FOREIGN KEY (`article_id`) REFERENCES `articles` (`id`) ON DELETE CASCADE,
  CONSTRAINT `article_topics_ibfk_2` FOREIGN KEY (`topic_id`) REFERENCES `topics` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文章话题关联表';

-- -----------------------------------------------------------------------------
-- topics 表 - 话题
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `topics`;
CREATE TABLE `topics` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL COMMENT '话题名称',
  `description` TEXT DEFAULT NULL COMMENT '话题描述',
  `keywords` JSON DEFAULT NULL COMMENT '关键词JSON数组',
  `is_auto_discovered` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否自动发现',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `created_by_user_id` BIGINT DEFAULT NULL COMMENT '创建者ID',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_topics_name` (`name`),
  KEY `ix_topics_is_active` (`is_active`),
  KEY `idx_topics_created_by` (`created_by_user_id`),
  CONSTRAINT `topics_ibfk_1` FOREIGN KEY (`created_by_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='话题表';

-- -----------------------------------------------------------------------------
-- topic_snapshots 表 - 话题快照
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `topic_snapshots`;
CREATE TABLE `topic_snapshots` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `topic_id` BIGINT NOT NULL COMMENT '话题ID',
  `snapshot_date` VARCHAR(10) NOT NULL COMMENT '快照日期 YYYY-MM-DD',
  `article_count` INT NOT NULL DEFAULT 0 COMMENT '文章数量',
  `trend_score` FLOAT NOT NULL DEFAULT 0 COMMENT '趋势分数',
  `trend` VARCHAR(10) NOT NULL DEFAULT 'stable' COMMENT '趋势: up, down, stable',
  `top_keywords` JSON DEFAULT NULL COMMENT '热门关键词',
  `summary` TEXT DEFAULT NULL COMMENT '摘要',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_topic_snapshots_topic_id` (`topic_id`),
  KEY `ix_topic_snapshots_snapshot_date` (`snapshot_date`),
  CONSTRAINT `topic_snapshots_ibfk_1` FOREIGN KEY (`topic_id`) REFERENCES `topics` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='话题快照表';

-- -----------------------------------------------------------------------------
-- event_clusters 表 - 事件聚类
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `event_clusters`;
CREATE TABLE `event_clusters` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `title` VARCHAR(255) NOT NULL COMMENT '事件标题',
  `description` TEXT DEFAULT NULL COMMENT '事件描述',
  `category` VARCHAR(50) DEFAULT NULL COMMENT '事件分类',
  `first_seen_at` DATETIME NOT NULL COMMENT '首次发现时间',
  `last_updated_at` DATETIME NOT NULL COMMENT '最后更新时间',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否活跃',
  `article_count` INT NOT NULL DEFAULT 0 COMMENT '文章数量',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_event_clusters_is_active` (`is_active`),
  KEY `ix_event_clusters_category` (`category`),
  KEY `ix_event_clusters_active_updated` (`is_active`, `last_updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='事件聚类表';

-- -----------------------------------------------------------------------------
-- event_members 表 - 事件成员
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `event_members`;
CREATE TABLE `event_members` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `event_id` BIGINT NOT NULL COMMENT '事件ID',
  `article_id` BIGINT NOT NULL COMMENT '文章ID',
  `similarity_score` FLOAT NOT NULL DEFAULT 0 COMMENT '相似度分数',
  `detection_method` VARCHAR(50) NOT NULL COMMENT '检测方法: keyword, entity, semantic, hybrid',
  `added_at` DATETIME NOT NULL COMMENT '加入时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_event_members_article_id` (`article_id`),
  KEY `ix_event_members_event_id` (`event_id`),
  CONSTRAINT `event_members_ibfk_1` FOREIGN KEY (`event_id`) REFERENCES `event_clusters` (`id`) ON DELETE CASCADE,
  CONSTRAINT `event_members_ibfk_2` FOREIGN KEY (`article_id`) REFERENCES `articles` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='事件成员表';

-- -----------------------------------------------------------------------------
-- reports 表 - 报告
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `reports`;
CREATE TABLE `reports` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` BIGINT NOT NULL COMMENT '用户ID',
  `type` VARCHAR(20) NOT NULL COMMENT '类型: weekly, monthly',
  `period_start` VARCHAR(10) NOT NULL COMMENT '开始日期 YYYY-MM-DD',
  `period_end` VARCHAR(10) NOT NULL COMMENT '结束日期 YYYY-MM-DD',
  `title` VARCHAR(255) NOT NULL COMMENT '标题',
  `content` TEXT NOT NULL COMMENT 'Markdown格式内容',
  `stats` JSON DEFAULT NULL COMMENT '统计数据',
  `generated_at` DATETIME NOT NULL COMMENT '生成时间',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_reports_user_id` (`user_id`),
  CONSTRAINT `reports_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报告表';

-- -----------------------------------------------------------------------------
-- rss_feeds 表 - RSS订阅源
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `rss_feeds`;
CREATE TABLE `rss_feeds` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `title` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '标题',
  `feed_url` VARCHAR(767) NOT NULL COMMENT 'Feed URL',
  `site_url` VARCHAR(767) NOT NULL DEFAULT '' COMMENT '网站URL',
  `category` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '分类',
  `description` TEXT DEFAULT NULL COMMENT '描述',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `last_fetched_at` DATETIME DEFAULT NULL COMMENT '最后抓取时间',
  `error_count` INT NOT NULL DEFAULT 0 COMMENT '错误次数',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `feed_url` (`feed_url`),
  KEY `idx_rss_feeds_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RSS订阅源表';

-- -----------------------------------------------------------------------------
-- arxiv_categories 表 - arXiv分类
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `arxiv_categories`;
CREATE TABLE `arxiv_categories` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `code` VARCHAR(50) NOT NULL COMMENT '分类代码',
  `name` VARCHAR(100) NOT NULL COMMENT '分类名称',
  `parent_code` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '父分类代码',
  `description` TEXT DEFAULT NULL COMMENT '描述',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  KEY `idx_arxiv_categories_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='arXiv分类表';

-- -----------------------------------------------------------------------------
-- wechat_accounts 表 - 微信公众号
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `wechat_accounts`;
CREATE TABLE `wechat_accounts` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL COMMENT '公众号名称',
  `account_id` VARCHAR(100) NOT NULL COMMENT '公众号ID',
  `description` TEXT DEFAULT NULL COMMENT '描述',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `last_fetched_at` DATETIME DEFAULT NULL COMMENT '最后抓取时间',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `account_id` (`account_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='微信公众号表';

-- -----------------------------------------------------------------------------
-- weibo_hot_searches 表 - 微博热搜榜单
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `weibo_hot_searches`;
CREATE TABLE `weibo_hot_searches` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `board_type` VARCHAR(50) NOT NULL COMMENT '榜单类型: realtimehot, socialevent, entrank, sport, game',
  `board_name` VARCHAR(100) NOT NULL COMMENT '榜单中文名称',
  `description` TEXT DEFAULT NULL COMMENT '榜单描述',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `last_fetched_at` DATETIME DEFAULT NULL COMMENT '最后抓取时间',
  `error_count` INT NOT NULL DEFAULT 0 COMMENT '连续错误次数',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `board_type` (`board_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='微博热搜榜单配置表';

-- -----------------------------------------------------------------------------
-- hackernews_sources 表 - HackerNews 板块配置
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `hackernews_sources`;
CREATE TABLE `hackernews_sources` (
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
DROP TABLE IF EXISTS `reddit_sources`;
CREATE TABLE `reddit_sources` (
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
DROP TABLE IF EXISTS `twitter_sources`;
CREATE TABLE `twitter_sources` (
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
-- user_subscriptions 表 - 用户订阅
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `user_subscriptions`;
CREATE TABLE `user_subscriptions` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` BIGINT NOT NULL COMMENT '用户ID',
  `source_type` VARCHAR(30) NOT NULL COMMENT '来源类型: arxiv_category, rss_feed, wechat_account, weibo_hot_search, hackernews_source, reddit_source, twitter_source',
  `source_id` BIGINT NOT NULL COMMENT '来源ID',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_subscription` (`user_id`, `source_type`, `source_id`),
  KEY `idx_user_subscriptions_source` (`source_type`, `source_id`),
  CONSTRAINT `user_subscriptions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户订阅表';

-- -----------------------------------------------------------------------------
-- backup_records 表 - 备份记录
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `backup_records`;
CREATE TABLE `backup_records` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `backup_date` DATETIME NOT NULL COMMENT '备份日期',
  `backup_file` VARCHAR(500) NOT NULL COMMENT '备份文件',
  `backup_size` BIGINT NOT NULL DEFAULT 0 COMMENT '备份大小(字节)',
  `article_count` INT NOT NULL DEFAULT 0 COMMENT '文章数量',
  `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '状态: pending, completed, failed',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `completed_at` DATETIME DEFAULT NULL COMMENT '完成时间',
  `error_message` TEXT DEFAULT NULL COMMENT '错误信息',
  PRIMARY KEY (`id`),
  UNIQUE KEY `backup_date` (`backup_date`),
  KEY `idx_backup_records_date` (`backup_date`),
  KEY `idx_backup_records_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='备份记录表';

-- -----------------------------------------------------------------------------
-- audit_logs 表 - 审计日志
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `audit_logs`;
CREATE TABLE `audit_logs` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` BIGINT DEFAULT NULL COMMENT '用户ID',
  `action` VARCHAR(100) NOT NULL COMMENT '操作',
  `resource_type` VARCHAR(50) NOT NULL COMMENT '资源类型',
  `resource_id` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '资源ID',
  `details` JSON DEFAULT NULL COMMENT '详情',
  `ip_address` VARCHAR(45) NOT NULL DEFAULT '' COMMENT 'IP地址',
  `user_agent` VARCHAR(500) NOT NULL DEFAULT '' COMMENT 'User Agent',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_audit_logs_user` (`user_id`),
  KEY `idx_audit_logs_action` (`action`),
  KEY `idx_audit_logs_created` (`created_at`),
  CONSTRAINT `audit_logs_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='审计日志表';

-- -----------------------------------------------------------------------------
-- token_usage_stats 表 - Token使用统计
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `token_usage_stats`;
CREATE TABLE `token_usage_stats` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `date` VARCHAR(10) NOT NULL COMMENT '日期 YYYY-MM-DD',
  `provider` VARCHAR(50) NOT NULL COMMENT 'AI提供商',
  `model` VARCHAR(100) NOT NULL COMMENT '模型名称',
  `total_calls` INT NOT NULL DEFAULT 0 COMMENT '总调用次数',
  `cached_calls` INT NOT NULL DEFAULT 0 COMMENT '缓存命中次数',
  `total_input_chars` INT NOT NULL DEFAULT 0 COMMENT '总输入字符数',
  `total_output_chars` INT NOT NULL DEFAULT 0 COMMENT '总输出字符数',
  `total_duration_ms` INT NOT NULL DEFAULT 0 COMMENT '总处理耗时(毫秒)',
  `failed_calls` INT NOT NULL DEFAULT 0 COMMENT '失败次数',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_token_usage_stats_date` (`date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Token使用统计表';

-- -----------------------------------------------------------------------------
-- system_config 表 - 系统配置
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `system_config`;
CREATE TABLE `system_config` (
  `config_key` VARCHAR(100) NOT NULL COMMENT '配置键',
  `config_value` TEXT NOT NULL COMMENT '配置值',
  `description` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '描述',
  `is_sensitive` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否敏感',
  `updated_by` BIGINT DEFAULT NULL COMMENT '更新者ID',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`config_key`),
  KEY `idx_system_config_updated_by` (`updated_by`),
  CONSTRAINT `system_config_ibfk_1` FOREIGN KEY (`updated_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统配置表';

-- -----------------------------------------------------------------------------
-- email_configs 表 - 邮件推送配置（支持多后端多配置）
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `email_configs`;
CREATE TABLE `email_configs` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  -- 后端类型与名称
  `backend_type` VARCHAR(20) NOT NULL DEFAULT 'smtp' COMMENT '后端类型: smtp, sendgrid, mailgun, brevo',
  `name` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '配置名称，如：主邮箱、备份邮箱',
  -- SMTP 配置
  `smtp_host` VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'SMTP服务器地址',
  `smtp_port` INT NOT NULL DEFAULT 587 COMMENT 'SMTP服务器端口',
  `smtp_user` VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'SMTP用户名',
  `smtp_password` VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'SMTP密码（加密存储）',
  `smtp_use_tls` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否使用TLS (STARTTLS)',
  `smtp_use_ssl` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否使用SSL直连',
  `smtp_ssl_ports` VARCHAR(50) NOT NULL DEFAULT '465' COMMENT 'SSL端口列表(逗号分隔)',
  -- SendGrid 配置
  `sendgrid_api_key` VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'SendGrid API密钥',
  -- Mailgun 配置
  `mailgun_api_key` VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Mailgun API密钥',
  `mailgun_domain` VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Mailgun域名',
  -- Brevo 配置
  `brevo_api_key` VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Brevo API密钥',
  `brevo_from_name` VARCHAR(100) NOT NULL DEFAULT 'ResearchPulse' COMMENT 'Brevo发件人名称',
  -- 推送设置
  `email_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否启用邮件通知（全局开关）',
  `sender_email` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '发件人邮箱地址',
  `push_frequency` VARCHAR(20) NOT NULL DEFAULT 'daily' COMMENT '推送频率: daily, weekly, instant',
  `push_time` VARCHAR(10) NOT NULL DEFAULT '09:00' COMMENT '推送时间（HH:MM格式）',
  `max_articles_per_email` INT NOT NULL DEFAULT 20 COMMENT '每封邮件最大文章数',
  -- 优先级与状态
  `priority` INT NOT NULL DEFAULT 0 COMMENT '优先级，数字越小越优先',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用此配置',
  -- 时间戳
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  INDEX `idx_backend_type` (`backend_type`),
  INDEX `idx_priority` (`priority`),
  INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='邮件推送配置表（支持多后端多配置）';

-- =============================================================================
-- 初始化数据
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 插入默认权限
-- -----------------------------------------------------------------------------
INSERT INTO `permissions` (`name`, `resource`, `action`, `description`) VALUES
-- 文章权限
('article:read', 'article', 'read', 'View articles'),
('article:list', 'article', 'list', 'List articles'),
-- 订阅权限
('subscription:create', 'subscription', 'create', 'Create subscriptions'),
('subscription:read', 'subscription', 'read', 'View own subscriptions'),
('subscription:delete', 'subscription', 'delete', 'Delete subscriptions'),
-- 用户管理权限
('user:manage', 'user', 'manage', 'Manage users'),
('user:list', 'user', 'list', 'List users'),
-- 角色管理权限
('role:manage', 'role', 'manage', 'Manage roles'),
('role:list', 'role', 'list', 'List roles'),
-- 爬虫管理权限
('crawler:manage', 'crawler', 'manage', 'Manage crawlers'),
('crawler:trigger', 'crawler', 'trigger', 'Trigger crawl tasks'),
-- 系统配置权限
('config:manage', 'config', 'manage', 'Manage system config'),
('config:read', 'config', 'read', 'Read system config'),
-- 备份权限
('backup:manage', 'backup', 'manage', 'Manage backups'),
('backup:restore', 'backup', 'restore', 'Restore from backup'),
-- AI处理权限
('ai:process', 'ai_processor', 'process', 'Trigger AI processing'),
('ai:view_stats', 'ai_processor', 'view_stats', 'View AI token statistics'),
-- 嵌入权限
('embedding:compute', 'embedding', 'compute', 'Compute article embeddings'),
('embedding:rebuild', 'embedding', 'rebuild', 'Rebuild Milvus index'),
-- 事件聚类权限
('event:read', 'event', 'read', 'View events'),
('event:cluster', 'event', 'cluster', 'Trigger event clustering'),
-- 话题权限
('topic:read', 'topic', 'read', 'View topics'),
('topic:manage', 'topic', 'manage', 'Create/update/delete topics'),
('topic:discover', 'topic', 'discover', 'Discover new topics'),
-- 行动项权限
('action:read', 'action', 'read', 'View own action items'),
('action:manage', 'action', 'manage', 'Create/update action items'),
-- 报告权限
('report:read', 'report', 'read', 'View reports'),
('report:generate', 'report', 'generate', 'Generate reports');

-- -----------------------------------------------------------------------------
-- 插入默认角色
-- -----------------------------------------------------------------------------
INSERT INTO `roles` (`name`, `description`) VALUES
('superuser', 'Superuser with all permissions'),
('admin', 'Administrator with management permissions'),
('user', 'Regular user with basic permissions'),
('guest', 'Guest user with read-only access');

-- -----------------------------------------------------------------------------
-- 分配角色权限 - superuser (所有权限)
-- -----------------------------------------------------------------------------
INSERT INTO `role_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id FROM `roles` r, `permissions` p WHERE r.name = 'superuser';

-- -----------------------------------------------------------------------------
-- 分配角色权限 - admin
-- -----------------------------------------------------------------------------
INSERT INTO `role_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id FROM `roles` r, `permissions` p 
WHERE r.name = 'admin' AND p.name IN (
    'article:read', 'article:list',
    'user:manage', 'user:list',
    'role:list',
    'crawler:manage', 'crawler:trigger',
    'config:read', 'config:manage',
    'backup:manage',
    'ai:process', 'ai:view_stats',
    'embedding:compute', 'embedding:rebuild',
    'event:read', 'event:cluster',
    'topic:read', 'topic:manage', 'topic:discover',
    'action:read', 'action:manage',
    'report:read', 'report:generate'
);

-- -----------------------------------------------------------------------------
-- 分配角色权限 - user
-- -----------------------------------------------------------------------------
INSERT INTO `role_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id FROM `roles` r, `permissions` p 
WHERE r.name = 'user' AND p.name IN (
    'article:read', 'article:list',
    'subscription:create', 'subscription:read', 'subscription:delete',
    'event:read',
    'topic:read',
    'action:read', 'action:manage',
    'report:read', 'report:generate'
);

-- -----------------------------------------------------------------------------
-- 分配角色权限 - guest
-- -----------------------------------------------------------------------------
INSERT INTO `role_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id FROM `roles` r, `permissions` p 
WHERE r.name = 'guest' AND p.name IN (
    'article:read', 'article:list'
);

-- -----------------------------------------------------------------------------
-- 插入 arXiv 分类数据
-- 注意: 所有分类默认不激活 (is_active=0)，只激活常用的 AI 相关分类
-- -----------------------------------------------------------------------------
INSERT INTO `arxiv_categories` (`code`, `name`, `parent_code`, `is_active`) VALUES
-- Computer Science - AI 相关分类（默认激活）
('cs.LG', 'Machine Learning', 'Computer Science', 1),
('cs.CV', 'Computer Vision and Pattern Recognition', 'Computer Science', 1),
('cs.CL', 'Computation and Language', 'Computer Science', 1),
('cs.IR', 'Information Retrieval', 'Computer Science', 1),
('cs.AI', 'Artificial Intelligence', 'Computer Science', 1),
('cs.NE', 'Neural and Evolutionary Computing', 'Computer Science', 1),
-- Computer Science - 其他分类（默认不激活）
('cs.DC', 'Distributed, Parallel, and Cluster Computing', 'Computer Science', 0),
('cs.RO', 'Robotics', 'Computer Science', 0),
('cs.SE', 'Software Engineering', 'Computer Science', 0),
('cs.DB', 'Databases', 'Computer Science', 0),
('cs.NI', 'Networking and Internet Architecture', 'Computer Science', 0),
('cs.CR', 'Cryptography and Security', 'Computer Science', 0),
('cs.HC', 'Human-Computer Interaction', 'Computer Science', 0),
('cs.IT', 'Information Theory', 'Computer Science', 0),
('cs.CY', 'Computers and Society', 'Computer Science', 0),
('cs.AR', 'Hardware Architecture', 'Computer Science', 0),
('cs.CG', 'Computational Geometry', 'Computer Science', 0),
('cs.FL', 'Formal Languages and Automata Theory', 'Computer Science', 0),
('cs.DS', 'Data Structures and Algorithms', 'Computer Science', 0),
('cs.CC', 'Computational Complexity', 'Computer Science', 0),
('cs.DL', 'Digital Libraries', 'Computer Science', 0),
('cs.LO', 'Logic in Computer Science', 'Computer Science', 0),
('cs.MA', 'Multiagent Systems', 'Computer Science', 0),
('cs.MM', 'Multimedia', 'Computer Science', 0),
('cs.OS', 'Operating Systems', 'Computer Science', 0),
('cs.PF', 'Performance', 'Computer Science', 0),
('cs.PL', 'Programming Languages', 'Computer Science', 0),
('cs.ET', 'Emerging Technologies', 'Computer Science', 0),
('cs.GR', 'Graphics', 'Computer Science', 0),
('cs.GT', 'Computer Science and Game Theory', 'Computer Science', 0),
('cs.MS', 'Mathematical Software', 'Computer Science', 0),
('cs.NA', 'Numerical Analysis', 'Computer Science', 0),
('cs.OH', 'Other Computer Science', 'Computer Science', 0),
('cs.SI', 'Social and Information Networks', 'Computer Science', 0),
('cs.SD', 'Sound', 'Computer Science', 0),
('cs.SC', 'Symbolic Computation', 'Computer Science', 0),
('cs.SY', 'Systems and Control', 'Computer Science', 0),
-- Mathematics（默认不激活）
('math.AG', 'Algebraic Geometry', 'Mathematics', 0),
('math.AT', 'Algebraic Topology', 'Mathematics', 0),
('math.AP', 'Analysis of PDEs', 'Mathematics', 0),
('math.CA', 'Classical Analysis and ODEs', 'Mathematics', 0),
('math.CO', 'Combinatorics', 'Mathematics', 0),
('math.AC', 'Commutative Algebra', 'Mathematics', 0),
('math.CV', 'Complex Variables', 'Mathematics', 0),
('math.DG', 'Differential Geometry', 'Mathematics', 0),
('math.DS', 'Dynamical Systems', 'Mathematics', 0),
('math.FA', 'Functional Analysis', 'Mathematics', 0),
('math.GM', 'General Mathematics', 'Mathematics', 0),
('math.GN', 'General Topology', 'Mathematics', 0),
('math.GT', 'Geometric Topology', 'Mathematics', 0),
('math.GR', 'Group Theory', 'Mathematics', 0),
('math.HO', 'History and Overview', 'Mathematics', 0),
('math.IT', 'Information Theory', 'Mathematics', 0),
('math.KT', 'K-Theory and Homology', 'Mathematics', 0),
('math.LO', 'Logic', 'Mathematics', 0),
('math.MP', 'Mathematical Physics', 'Mathematics', 0),
('math.MG', 'Metric Geometry', 'Mathematics', 0),
('math.NT', 'Number Theory', 'Mathematics', 0),
('math.NA', 'Numerical Analysis', 'Mathematics', 0),
('math.OA', 'Operator Algebras', 'Mathematics', 0),
('math.PR', 'Probability', 'Mathematics', 0),
('math.QA', 'Quantum Algebra', 'Mathematics', 0),
('math.RT', 'Representation Theory', 'Mathematics', 0),
('math.RA', 'Rings and Algebras', 'Mathematics', 0),
('math.SP', 'Spectral Theory', 'Mathematics', 0),
('math.ST', 'Statistics Theory', 'Mathematics', 0),
('math.SG', 'Symplectic Geometry', 'Mathematics', 0),
-- Physics - Astrophysics（默认不激活）
('astro-ph.CO', 'Cosmology and Nongalactic Astrophysics', 'Physics', 0),
('astro-ph.EP', 'Earth and Planetary Astrophysics', 'Physics', 0),
('astro-ph.GA', 'Astrophysics of Galaxies', 'Physics', 0),
('astro-ph.HE', 'High Energy Astrophysical Phenomena', 'Physics', 0),
('astro-ph.IM', 'Instrumentation and Methods for Astrophysics', 'Physics', 0),
('astro-ph.SR', 'Solar and Stellar Astrophysics', 'Physics', 0),
-- Physics - Condensed Matter（默认不激活）
('cond-mat.dis-nn', 'Disordered Systems and Neural Networks', 'Physics', 0),
('cond-mat.mes-hall', 'Mesoscale and Nanoscale Physics', 'Physics', 0),
('cond-mat.mtrl-sci', 'Materials Science', 'Physics', 0),
('cond-mat.other', 'Other Condensed Matter', 'Physics', 0),
('cond-mat.quant-gas', 'Quantum Gases', 'Physics', 0),
('cond-mat.soft', 'Soft Condensed Matter', 'Physics', 0),
('cond-mat.stat-mech', 'Statistical Mechanics', 'Physics', 0),
('cond-mat.str-el', 'Strongly Correlated Electrons', 'Physics', 0),
('cond-mat.supr-con', 'Superconductivity', 'Physics', 0),
-- Physics - Other（默认不激活）
('gr-qc', 'General Relativity and Quantum Cosmology', 'Physics', 0),
('hep-ex', 'High Energy Physics - Experiment', 'Physics', 0),
('hep-lat', 'High Energy Physics - Lattice', 'Physics', 0),
('hep-ph', 'High Energy Physics - Phenomenology', 'Physics', 0),
('hep-th', 'High Energy Physics - Theory', 'Physics', 0),
('math-ph', 'Mathematical Physics', 'Physics', 0),
('nlin.AO', 'Adaptation and Self-Organizing Systems', 'Physics', 0),
('nlin.CD', 'Chaotic Dynamics', 'Physics', 0),
('nlin.CG', 'Cellular Automata and Lattice Gases', 'Physics', 0),
('nlin.PS', 'Pattern Formation and Solitons', 'Physics', 0),
('nlin.SI', 'Exactly Solvable and Integrable Systems', 'Physics', 0),
('nucl-ex', 'Nuclear Experiment', 'Physics', 0),
('nucl-th', 'Nuclear Theory', 'Physics', 0),
('physics.acc-ph', 'Accelerator Physics', 'Physics', 0),
('physics.ao-ph', 'Atmospheric and Oceanic Physics', 'Physics', 0),
('physics.app-ph', 'Applied Physics', 'Physics', 0),
('physics.atm-clus', 'Atomic and Molecular Clusters', 'Physics', 0),
('physics.atom-ph', 'Atomic Physics', 'Physics', 0),
('physics.bio-ph', 'Biological Physics', 'Physics', 0),
('physics.chem-ph', 'Chemical Physics', 'Physics', 0),
('physics.class-ph', 'Classical Physics', 'Physics', 0),
('physics.data-an', 'Data Analysis, Statistics and Probability', 'Physics', 0),
('physics.ed-ph', 'Physics Education', 'Physics', 0),
('physics.flu-dyn', 'Fluid Dynamics', 'Physics', 0),
('physics.gen-ph', 'General Physics', 'Physics', 0),
('physics.geo-ph', 'Geophysics', 'Physics', 0),
('physics.hist-ph', 'History and Philosophy of Physics', 'Physics', 0),
('physics.ins-det', 'Instrumentation and Detectors', 'Physics', 0),
('physics.med-ph', 'Medical Physics', 'Physics', 0),
('physics.optics', 'Optics', 'Physics', 0),
('physics.plasm-ph', 'Plasma Physics', 'Physics', 0),
('physics.pop-ph', 'Popular Physics', 'Physics', 0),
('physics.soc-ph', 'Physics and Society', 'Physics', 0),
('physics.space-ph', 'Space Physics', 'Physics', 0),
('quant-ph', 'Quantum Physics', 'Physics', 0),
('physics.comp-ph', 'Computational Physics', 'Physics', 0),
-- Statistics（默认不激活）
('stat.AP', 'Applications', 'Statistics', 0),
('stat.CO', 'Computation', 'Statistics', 0),
('stat.ME', 'Methodology', 'Statistics', 0),
('stat.TH', 'Statistics Theory', 'Statistics', 0),
('stat.OT', 'Other Statistics', 'Statistics', 0),
('stat.ML', 'Machine Learning', 'Statistics', 0),
-- Electrical Engineering（默认不激活）
('eess.AS', 'Audio and Speech Processing', 'Electrical Engineering', 0),
('eess.IV', 'Image and Video Processing', 'Electrical Engineering', 0),
('eess.SP', 'Signal Processing', 'Electrical Engineering', 0),
('eess.SY', 'Systems and Control', 'Electrical Engineering', 0),
-- Economics（默认不激活）
('econ.EM', 'Econometrics', 'Economics', 0),
('econ.GN', 'General Economics', 'Economics', 0),
('econ.TH', 'Theoretical Economics', 'Economics', 0),
-- Quantitative Biology（默认不激活）
('q-bio.BM', 'Biomolecules', 'Quantitative Biology', 0),
('q-bio.CB', 'Cell Behavior', 'Quantitative Biology', 0),
('q-bio.GN', 'Genomics', 'Quantitative Biology', 0),
('q-bio.MN', 'Molecular Networks', 'Quantitative Biology', 0),
('q-bio.NC', 'Neurons and Cognition', 'Quantitative Biology', 0),
('q-bio.OT', 'Other Quantitative Biology', 'Quantitative Biology', 0),
('q-bio.PE', 'Populations and Evolution', 'Quantitative Biology', 0),
('q-bio.SC', 'Subcellular Processes', 'Quantitative Biology', 0),
('q-bio.TO', 'Tissues and Organs', 'Quantitative Biology', 0),
('q-bio.QM', 'Quantitative Methods', 'Quantitative Biology', 0),
-- Quantitative Finance（默认不激活）
('q-fin.CP', 'Computational Finance', 'Quantitative Finance', 0),
('q-fin.EC', 'Economics', 'Quantitative Finance', 0),
('q-fin.GN', 'General Finance', 'Quantitative Finance', 0),
('q-fin.MF', 'Mathematical Finance', 'Quantitative Finance', 0),
('q-fin.PM', 'Portfolio Management', 'Quantitative Finance', 0),
('q-fin.PR', 'Pricing of Securities', 'Quantitative Finance', 0),
('q-fin.RM', 'Risk Management', 'Quantitative Finance', 0),
('q-fin.ST', 'Statistical Finance', 'Quantitative Finance', 0),
('q-fin.TR', 'Trading and Market Microstructure', 'Quantitative Finance', 0);

-- -----------------------------------------------------------------------------
-- 插入 RSS 订阅源数据
-- 注意: 只有以下源默认启用(is_active=1), 其他源保留但默认不抓取(is_active=0):
--   量子位、36氪资讯、虎嗅网、机器之心、美团技术团队
-- -----------------------------------------------------------------------------
INSERT INTO `rss_feeds` (`title`, `feed_url`, `site_url`, `category`, `is_active`) VALUES
-- 其他 (默认不抓取)
('The Guardian/World', 'https://www.theguardian.com/world/rss', '', '其他', 0),
('New Yorker: Culture', 'https://www.newyorker.com/feed/everything', '', '其他', 0),
('博海拾贝', 'https://bohaishibei.com/feed/', '', '其他', 0),
('The Atlantic', 'https://www.theatlantic.com/feed/all/', '', '其他', 0),
('中英文双语新闻 热词翻译- 中国日报21世纪英文报', 'http://www.chinadaily.com.cn/rss/china_rss.xml', '', '其他', 0),
('运营派', 'https://www.yunyingpai.com/feed', '', '其他', 0),
('TIME', 'http://feeds.feedburner.com/time/topstories', '', '其他', 0),
('The Washington Post', 'http://feeds.washingtonpost.com/rss/world', '', '其他', 0),
('最新更新 – Solidot', 'https://www.solidot.org/index.rss', '', '其他', 0),
('量子位', 'https://www.qbitai.com/feed', '', '其他', 1),
('36氪资讯 - 推荐', 'https://36kr.com/feed', '', '其他', 1),
('掘金阅读 - rsshub', 'https://juejin.cn/rss', '', '其他', 0),
('CNN/Business', 'http://rss.cnn.com/rss/edition.rss', '', '其他', 0),
('IT之家-24 小时最热', 'https://www.ithome.com/rss/', '', '其他', 0),
('虎嗅网 - 首页资讯 - rsshub', 'https://www.huxiu.com/rss/0.xml', '', '其他', 1),
('Nature Communications', 'http://feeds.nature.com/nature/rss/current', '', '其他', 0),
('热门文章 - 人人都是产品经理', 'http://www.woshipm.com/feed', '', '其他', 0),
('TechNews 科技新報', 'https://techcrunch.com/feed/', '', '其他', 0),
('人民论坛评论_人民论坛网_中央重点理论网站_人民日报社主管', 'http://www.people.com.cn/rss/politics.xml', '', '其他', 0),
('时政频道_新华网', 'http://www.xinhuanet.com/politics/news_politics.xml', '', '其他', 0),
('文章 | 机核 GCORES - rsshub', 'https://www.gcores.com/rss', '', '其他', 0),
('WIRED / Tech', 'https://www.wired.com/feed/rss', '', '其他', 0),
('Scientific American Content: Global', 'https://www.science.org/rss/news_current.xml', '', '其他', 0),
('Top News - MIT Technology Review', 'https://www.technologyreview.com/feed/', '', '其他', 0),
('NYT > World News', 'https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml', '', '其他', 0),
-- 科技 (默认不抓取)
('爱范儿', 'https://www.ifanr.com/feed', '', '科技', 0),
('数字尾巴', 'https://www.dgtle.com/rss/dgtle.xml', '', '科技', 0),
('小众软件', 'https://www.appinn.com/feed/', '', '科技', 0),
('机器之心', 'https://www.jiqizhixin.com/rss', '', '科技', 1),
('V2EX - 分享创造', 'https://www.v2ex.com/index.xml', '', '科技', 0),
('钛媒体：引领未来商业与生活新知', 'https://www.tmtpost.com/rss.xml', '', '科技', 0),
('异次元软件世界', 'https://www.iplaysoft.com/feed', '', '科技', 0),
('小道消息', 'https://happyxiao.com/feed/', '', '科技', 0),
-- 科学 (默认不抓取)
('cs.CV@arXiv.org', 'http://export.arxiv.org/rss/cs', '', '科学', 0),
-- 商业财经 (默认不抓取)
('经济观察报', 'http://www.eeo.com.cn/rss.xml', '', '商业财经', 0),
-- 游戏 (默认不抓取)
('触乐', 'https://www.chuapp.com/feed', '', '游戏', 0),
('游研社', 'https://www.yystv.cn/rss/feed', '', '游戏', 0),
-- IT/软件开发 (默认不抓取)
('阮一峰的网络日志', 'https://www.ruanyifeng.com/blog/atom.xml', '', 'IT/软件开发', 0),
-- 科技新闻 (默认不抓取)
('New York Times Tech', 'https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml', '', '科技新闻', 0),
('TechCrunch', 'https://techcrunch.com/feed', '', '科技新闻', 0),
-- 开发者 (默认不抓取)
('GitHub Blog', 'https://github.blog/feed', '', '开发者', 0),
('Stack Overflow Blog', 'https://stackoverflow.blog/feed', '', '开发者', 0),
-- 生活 (默认不抓取)
('理想生活实验室', 'https://www.toodaylab.com/feed', '', '生活', 0),
('Lifehacker', 'https://lifehacker.com/rss', '', '生活', 0),
-- 读书/文化 (默认不抓取)
('扯氮集', 'http://weiwuhui.com/feed', '', '读书/文化', 0),
('海德沙龙（HeadSalon）', 'http://headsalon.org/feed', '', '读书/文化', 0),
-- 技术社区 (默认不抓取)
('Hacker News', 'https://news.ycombinator.com/rss', '', '技术社区', 0),
-- 消费科技 (默认不抓取)
('The Verge', 'https://www.theverge.com/rss/index.xml', '', '消费科技', 0),
-- 新闻媒体 (默认不抓取)
('联合早报', 'https://plink.anyfeeder.com/zaobao/realtime/china', '', '新闻媒体', 0),
-- 前沿科技 (默认不抓取)
('MIT Technology Review', 'https://www.technologyreview.com/feed', '', '前沿科技', 0),
-- 技术与社会 (默认不抓取)
('编程随想的博客', 'https://feeds2.feedburner.com/programthink', '', '技术与社会', 0),
-- 设计与开发 (默认不抓取)
('Smashing Magazine', 'https://www.smashingmagazine.com/feed', '', '设计与开发', 0),
-- 效率工具 (默认不抓取)
('少数派', 'https://sspai.com/feed', '', '效率工具', 0),
-- IT专业 (默认不抓取)
('TechRepublic', 'https://www.techrepublic.com/rssfeeds/articles', '', 'IT专业', 0),
-- 前端开发 (默认不抓取)
('CSS-Tricks', 'https://css-tricks.com/feed', '', '前端开发', 0),
-- 技术博客 (默认不抓取)
('酷壳 CoolShell', 'https://coolshell.cn/feed', '', '技术博客', 0),
-- 网页设计 (默认不抓取)
('A List Apart', 'https://alistapart.com/main/feed', '', '网页设计', 0),
-- 互联网 (默认不抓取)
('月光博客', 'https://www.williamlong.info/rss.xml', '', '互联网', 0),
-- 技术团队
('美团技术团队', 'https://tech.meituan.com/feed', '', '技术团队', 1);

-- -----------------------------------------------------------------------------
-- 插入微博热搜榜单数据
-- 注意: 除热搜榜外，其他榜单需要配置登录 Cookie 才能抓取，默认禁用
-- -----------------------------------------------------------------------------
INSERT INTO `weibo_hot_searches` (`board_type`, `board_name`, `description`, `is_active`) VALUES
('realtimehot', '热搜榜', '微博实时热搜榜单（公开接口，无需登录）', 1),
('socialevent', '要闻榜', '微博社会要闻榜单（需要登录Cookie）', 0),
('entrank', '文娱榜', '微博文娱热点榜单（需要登录Cookie）', 0),
('sport', '体育榜', '微博体育热点榜单（需要登录Cookie）', 0),
('game', '游戏榜', '微博游戏热点榜单（需要登录Cookie）', 0);

-- -----------------------------------------------------------------------------
-- 插入 HackerNews 板块数据
-- 注意: 使用 hnrss.org RSS Feed，无需 API Key
-- -----------------------------------------------------------------------------
INSERT INTO `hackernews_sources` (`feed_type`, `feed_name`, `description`, `is_active`) VALUES
('front', 'HackerNews 首页', 'HackerNews 首页热门帖子', 1),
('new', 'HackerNews 最新', 'HackerNews 最新帖子', 0),
('best', 'HackerNews 精选', 'HackerNews 历史精选帖子', 0),
('ask', 'Ask HN', 'Ask HackerNews 问答帖子', 0),
('show', 'Show HN', 'Show HackerNews 项目展示帖子', 0);

-- -----------------------------------------------------------------------------
-- 插入 Reddit 示例订阅源数据
-- 注意: 使用 Reddit 官方 RSS Feed，无需 API Key
-- -----------------------------------------------------------------------------
INSERT INTO `reddit_sources` (`source_type`, `source_name`, `display_name`, `description`, `is_active`) VALUES
-- 示例 Subreddit（默认禁用，管理员可根据需要启用）
('subreddit', 'programming', 'r/programming', '编程相关讨论', 0),
('subreddit', 'MachineLearning', 'r/MachineLearning', '机器学习研究', 0),
('subreddit', 'artificial', 'r/artificial', '人工智能讨论', 0);

-- -----------------------------------------------------------------------------
-- 插入 Twitter 示例订阅源数据
-- 注意: 需要配置 TwitterAPI.io API Key (环境变量 TWITTERAPI_IO_KEY)
-- -----------------------------------------------------------------------------
-- Twitter 示例源（默认禁用，需要配置 API Key 后启用）
-- INSERT INTO `twitter_sources` (`username`, `display_name`, `description`, `is_active`) VALUES
-- ('elonmusk', 'Elon Musk', '特斯拉、SpaceX CEO', 0);

-- -----------------------------------------------------------------------------
-- 插入系统配置数据
-- -----------------------------------------------------------------------------
INSERT INTO `system_config` (`config_key`, `config_value`, `description`, `is_sensitive`) VALUES
-- AI 配置
('ai.provider', 'ollama', 'AI provider: ollama, openai, claude', 0),
('ai.ollama_base_url', 'http://localhost:11434', 'Ollama API base URL', 0),
('ai.ollama_model', 'qwen3:32b', 'Ollama model name', 0),
('ai.ollama_model_light', '', 'Ollama light model for simple tasks', 0),
('ai.ollama_timeout', '120', 'Ollama request timeout in seconds', 0),
('ai.openai_model', 'gpt-4o', 'OpenAI model name', 0),
('ai.openai_model_light', 'gpt-4o-mini', 'OpenAI light model name', 0),
('ai.openai_timeout', '60', 'OpenAI request timeout in seconds', 0),
('ai.claude_model', 'claude-sonnet-4-20250514', 'Claude model name', 0),
('ai.claude_model_light', 'claude-haiku-4-20250514', 'Claude light model name', 0),
('ai.claude_timeout', '60', 'Claude request timeout in seconds', 0),
('ai.cache_enabled', 'true', 'Enable AI result caching', 0),
('ai.cache_ttl', '86400', 'AI cache TTL in seconds', 0),
('ai.max_content_length', '1500', 'Max content length for AI processing', 0),
('ai.max_title_length', '200', 'Max title length for AI processing', 0),
('ai.thinking_enabled', 'false', 'Enable extended thinking mode', 0),
('ai.concurrent_enabled', 'false', 'Enable concurrent AI processing', 0),
('ai.workers_heavy', '2', 'Number of workers for heavy AI tasks', 0),
('ai.workers_screen', '4', 'Number of workers for screening tasks', 0),
-- Embedding 配置
('embedding.provider', 'sentence-transformers', 'Embedding provider', 0),
('embedding.model', 'all-MiniLM-L6-v2', 'Embedding model name', 0),
('embedding.dimension', '384', 'Embedding vector dimension', 0),
('embedding.milvus_host', 'localhost', 'Milvus server host', 0),
('embedding.milvus_port', '19530', 'Milvus server port', 0),
('embedding.milvus_collection', 'article_embeddings', 'Milvus collection name', 0),
('embedding.similarity_threshold', '0.85', 'Similarity threshold', 0),
-- Event 配置
('event.min_similarity', '0.7', 'Minimum similarity threshold', 0),
('event.rule_weight', '0.4', 'Rule-based weight for clustering', 0),
('event.semantic_weight', '0.6', 'Semantic weight for clustering', 0),
-- Feature toggles
('feature.crawler', 'true', 'Article crawler', 0),
('feature.backup', 'true', 'Database backup', 0),
('feature.cleanup', 'true', 'Data cleanup', 0),
('feature.ai_processor', 'false', 'AI processing', 0),
('feature.embedding', 'false', 'Embedding / Milvus', 0),
('feature.event_clustering', 'false', 'Event clustering', 0),
('feature.topic_radar', 'false', 'Topic radar', 0),
('feature.action_items', 'false', 'Action items', 0),
('feature.report_generation', 'false', 'Report generation', 0),
('feature.email_notification', 'false', 'Email notifications', 0),
-- Scheduler 配置
('scheduler.crawl_interval_hours', '6', 'Crawl interval in hours', 0),
('scheduler.ai_process_interval_hours', '1', 'AI processing interval in hours', 0),
('scheduler.embedding_interval_hours', '2', 'Embedding computation interval in hours', 0),
('scheduler.event_cluster_hour', '2', 'Hour of day to run event clustering (0-23)', 0),
('scheduler.topic_discovery_day', 'mon', 'Day of week for topic discovery', 0),
('scheduler.topic_discovery_hour', '1', 'Hour of day for topic discovery (0-23)', 0),
('scheduler.backup_hour', '4', 'Hour of day to run backup (0-23)', 0),
('scheduler.cleanup_hour', '3', 'Hour of day to run cleanup (0-23)', 0);

-- =============================================================================
-- Superuser 配置说明
-- =============================================================================
-- Superuser 账户需要通过应用程序创建，不在 SQL 脚本中硬编码密码。
-- 
-- 配置方式：
-- 1. 在 .env 文件中设置以下环境变量：
--    SUPERUSER_USERNAME=superuser
--    SUPERUSER_EMAIL=superuser@example.com
--    SUPERUSER_PASSWORD=YourSecurePassword123
--
-- 2. 或者在环境变量中设置：
--    export SUPERUSER_USERNAME=superuser
--    export SUPERUSER_EMAIL=superuser@example.com
--    export SUPERUSER_PASSWORD=YourSecurePassword123
--
-- 3. 应用启动时会自动检查并创建 superuser 账户
--    参见: main.py 中的 init_default_data() 函数
--
-- 安全建议：
-- - 不要在代码或配置文件中硬编码密码
-- - 使用强密码（至少12位，包含大小写字母、数字和特殊字符）
-- - 生产环境建议定期更换密码
-- =============================================================================

-- 恢复外键检查
SET FOREIGN_KEY_CHECKS = 1;

-- 初始化完成
SELECT 'Database initialization completed successfully!' AS status;
