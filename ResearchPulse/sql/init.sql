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
  `translated_title` VARCHAR(500) DEFAULT NULL COMMENT '翻译后的中文标题',
  `content` TEXT NOT NULL COMMENT '内容',
  `cover_image_url` VARCHAR(2000) NOT NULL DEFAULT '' COMMENT '封面图片URL',
  `category` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '分类',
  -- 新闻专用字段
  `news_source_country` VARCHAR(5) DEFAULT NULL COMMENT '新闻来源国家: CN, EN, 非新闻为NULL',
  `news_category` VARCHAR(50) DEFAULT NULL COMMENT '新闻分类: tech, finance, general等',
  `image_url` VARCHAR(2000) DEFAULT NULL COMMENT '文章封面图片URL',
  `source_crawler_type` VARCHAR(20) DEFAULT NULL COMMENT '爬虫类型: rss, cn_news, arxiv等',
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
  `arxiv_paper_type` VARCHAR(20) DEFAULT '' COMMENT 'arXiv 论文类型: new/updated',
  -- 微信专用字段
  `wechat_account_name` VARCHAR(200) DEFAULT NULL COMMENT '微信公众号名称',
  `wechat_digest` TEXT DEFAULT NULL COMMENT '微信摘要',
  -- AI 处理结果字段
  `content_summary` TEXT DEFAULT NULL COMMENT 'AI摘要或翻译',
  `ai_summary` TEXT DEFAULT NULL COMMENT 'AI中文摘要',
  `ai_category` VARCHAR(50) DEFAULT NULL COMMENT 'AI主分类',
  `ai_subcategory` VARCHAR(50) DEFAULT NULL COMMENT 'AI子分类',
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
  KEY `ix_articles_category` (`category`),
  -- 复合索引：优化 AI 处理和 Embedding 任务的未处理文章查询
  -- 覆盖 WHERE ai_processed_at IS NULL AND is_archived = FALSE ORDER BY crawl_time DESC
  KEY `ix_articles_ai_unprocessed` (`ai_processed_at`, `is_archived`, `crawl_time`),
  KEY `ix_articles_news_source_country` (`news_source_country`),
  KEY `ix_articles_news_category` (`news_category`),
  KEY `ix_articles_news_country_category` (`news_source_country`, `news_category`)
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
-- -----------------------------------------------------------------------------
-- content_themes 表 - 通用内容主题
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `content_themes`;
CREATE TABLE `content_themes` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(50) NOT NULL COMMENT '主题唯一标识符，如 classic_blue',
  `display_name` VARCHAR(100) NOT NULL COMMENT '界面显示名称，如 经典蓝',
  `description` VARCHAR(200) DEFAULT NULL COMMENT '主题描述',
  `content_types` JSON NOT NULL COMMENT '适用内容类型列表，如 ["daily_report", "weekly_report"]',
  `formatter_types` JSON NOT NULL COMMENT '适用格式化器类型，如 ["wechat_html", "email_html"]',
  `config` JSON NOT NULL COMMENT '主题配置 JSON，包含 colors、typography、effects 子对象',
  `is_default` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为默认主题',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `priority` INT NOT NULL DEFAULT 0 COMMENT '排序优先级，越大越靠前',
  `preview_url` VARCHAR(500) DEFAULT NULL COMMENT '预览图 URL',
  `author` VARCHAR(100) DEFAULT NULL COMMENT '主题作者',
  `created_at` DATETIME(6) NOT NULL,
  `updated_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_content_themes_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='通用内容主题表，支持日报、周报、邮件等所有内容类型';

-- -----------------------------------------------------------------------------
-- reports 表 - 周报/月报
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
  `theme_id` INT DEFAULT NULL COMMENT '关联的内容主题',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_reports_user_id` (`user_id`),
  KEY `ix_reports_theme_id` (`theme_id`),
  CONSTRAINT `reports_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_reports_theme_id` FOREIGN KEY (`theme_id`) REFERENCES `content_themes` (`id`) ON DELETE SET NULL
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
  `country` VARCHAR(5) DEFAULT NULL COMMENT '新闻源国家: CN, EN, null表示非新闻类',
  `news_category` VARCHAR(50) DEFAULT NULL COMMENT '新闻分类: general/tech/finance等',
  `feed_format` VARCHAR(10) NOT NULL DEFAULT 'rss' COMMENT 'Feed 格式: rss(XML/Atom), json(JSON API)',
  `json_config` TEXT DEFAULT NULL COMMENT 'JSON Feed 解析配置（仅 feed_format=json 时使用）',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `feed_url` (`feed_url`),
  KEY `idx_rss_feeds_category` (`category`),
  KEY `idx_rss_feeds_country` (`country`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RSS订阅源表';

-- -----------------------------------------------------------------------------
-- arxiv_categories 表 - arXiv分类
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `arxiv_categories`;
CREATE TABLE `arxiv_categories` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `code` VARCHAR(50) NOT NULL COMMENT '分类代码',
  `name` VARCHAR(100) NOT NULL COMMENT '分类名称（英文）',
  `name_zh` VARCHAR(100) DEFAULT '' COMMENT '分类中文名称',
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
-- daily_reports 表 - 每日报告（支持多数据源）
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `daily_reports`;
CREATE TABLE `daily_reports` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `report_date` DATE NOT NULL COMMENT '报告日期',
  `source_type` VARCHAR(20) NOT NULL DEFAULT 'arxiv' COMMENT '数据源类型: arxiv, hackernews, reddit, weibo, rss',
  `category` VARCHAR(50) NOT NULL COMMENT '分类代码，如 cs.LG, cs.CV, technology',
  `category_name` VARCHAR(100) NOT NULL COMMENT '分类中文名称，如 机器学习',
  `title` VARCHAR(200) NOT NULL COMMENT '报告标题',
  `content_markdown` MEDIUMTEXT NOT NULL COMMENT 'Markdown 格式的报告内容',
  `content_wechat` MEDIUMTEXT DEFAULT NULL COMMENT '微信公众号专用格式内容',
  `article_count` INT NOT NULL DEFAULT 0 COMMENT '收录文章数量',
  `article_ids` JSON DEFAULT NULL COMMENT '收录的文章 ID 列表',
  `status` VARCHAR(20) NOT NULL DEFAULT 'draft' COMMENT '状态: draft/published/archived',
  `published_at` DATETIME DEFAULT NULL COMMENT '发布时间',
  `wechat_draft_media_id` VARCHAR(128) DEFAULT NULL COMMENT '微信草稿 media_id',
  `wechat_push_status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '微信推送状态: pending/success/failed/skipped',
  `wechat_push_error` TEXT DEFAULT NULL COMMENT '微信推送错误信息',
  `wechat_pushed_at` DATETIME DEFAULT NULL COMMENT '微信推送时间',
  `sync_status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '跨服务器同步状态: pending/success/failed/skipped',
  `sync_error` TEXT DEFAULT NULL COMMENT '同步失败时的错误信息',
  `sync_attempted_at` DATETIME DEFAULT NULL COMMENT '最后一次同步尝试的时间',
  `wechat_theme_id` INT DEFAULT NULL COMMENT '关联的微信 HTML 主题',
  `wechat_scheduled_push_time` DATETIME(6) DEFAULT NULL COMMENT '定时推送时间，为 null 表示未设置',
  `wechat_scheduled_push_job_id` VARCHAR(200) DEFAULT NULL COMMENT 'APScheduler job_id，用于取消定时推送任务',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_daily_reports_date_source_category` (`report_date`, `source_type`, `category`),
  KEY `ix_daily_reports_status` (`status`),
  KEY `ix_daily_reports_wechat_push_status` (`wechat_push_status`),
  KEY `ix_daily_reports_source_type` (`source_type`),
  KEY `ix_daily_reports_sync_status` (`sync_status`),
  KEY `ix_daily_reports_wechat_theme_id` (`wechat_theme_id`),
  CONSTRAINT `fk_daily_reports_wechat_theme` FOREIGN KEY (`wechat_theme_id`) REFERENCES `content_themes` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='每日报告表（支持多数据源）';

-- -----------------------------------------------------------------------------
-- wechat_accounts 表 - 微信公众号
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `wechat_accounts`;
CREATE TABLE `wechat_accounts` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_name` VARCHAR(100) NOT NULL COMMENT '微信公众号唯一标识(biz)',
  `display_name` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '显示名称',
  `description` TEXT DEFAULT NULL COMMENT '描述',
  `avatar_url` VARCHAR(2000) NOT NULL DEFAULT '' COMMENT '头像URL',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `last_fetched_at` DATETIME DEFAULT NULL COMMENT '最后抓取时间',
  `error_count` INT NOT NULL DEFAULT 0 COMMENT '连续错误次数',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `account_name` (`account_name`),
  KEY `idx_wechat_accounts_active` (`is_active`)
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
-- news_sources 表 - HTML新闻源配置（CSS选择器存数据库）
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `news_sources`;
CREATE TABLE `news_sources` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL COMMENT '站点名称',
  `site_url` VARCHAR(2000) NOT NULL COMMENT '站点首页URL',
  `list_url` VARCHAR(2000) NOT NULL COMMENT '文章列表页URL',
  `selectors` JSON NOT NULL COMMENT 'CSS选择器配置JSON',
  `country` VARCHAR(5) NOT NULL DEFAULT 'CN' COMMENT '国家: CN 或 EN',
  `news_category` VARCHAR(50) NOT NULL DEFAULT 'general' COMMENT '新闻分类: general, tech, finance等',
  `encoding` VARCHAR(20) NOT NULL DEFAULT 'utf-8' COMMENT '页面编码: utf-8, gbk等',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `last_fetched_at` DATETIME DEFAULT NULL COMMENT '最后抓取时间',
  `error_count` INT NOT NULL DEFAULT 0 COMMENT '连续错误次数',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='HTML新闻源配置表';

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
  `completed_at` DATETIME DEFAULT NULL COMMENT '完成时间',
  `error_message` TEXT DEFAULT NULL COMMENT '错误信息',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
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
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
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

-- -----------------------------------------------------------------------------
-- background_tasks 表 - 后台任务追踪
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `background_tasks`;
CREATE TABLE `background_tasks` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `task_id` VARCHAR(36) NOT NULL COMMENT '任务唯一标识符（UUID）',
  `task_type` VARCHAR(50) NOT NULL COMMENT '任务类型（如 daily_report, ai_pipeline）',
  `name` VARCHAR(255) NOT NULL COMMENT '任务名称/描述',
  `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '状态: pending/running/completed/failed/cancelled',
  `progress` INT NOT NULL DEFAULT 0 COMMENT '进度百分比（0-100）',
  `progress_message` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '进度消息',
  `params` JSON DEFAULT NULL COMMENT '任务参数',
  `result` JSON DEFAULT NULL COMMENT '任务结果',
  `error_message` TEXT DEFAULT NULL COMMENT '错误信息',
  `created_by` INT DEFAULT NULL COMMENT '创建者用户ID',
  `started_at` DATETIME DEFAULT NULL COMMENT '任务开始时间',
  `completed_at` DATETIME DEFAULT NULL COMMENT '任务完成时间',
  `is_read` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已读',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_background_tasks_task_id` (`task_id`),
  KEY `ix_background_tasks_type` (`task_type`),
  KEY `ix_background_tasks_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='后台任务追踪表';

-- -----------------------------------------------------------------------------
-- pipeline_tasks 表 - 流水线任务队列
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `pipeline_tasks`;
CREATE TABLE `pipeline_tasks` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `stage` VARCHAR(32) NOT NULL COMMENT '阶段: ai, embedding, event, action',
  `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '状态: pending, running, completed, failed',
  `priority` INT NOT NULL DEFAULT 0 COMMENT '优先级（越大越优先）',
  `payload` JSON DEFAULT NULL COMMENT '任务载荷',
  `result` JSON DEFAULT NULL COMMENT '执行结果',
  `error_message` TEXT DEFAULT NULL COMMENT '错误信息',
  `retry_count` INT NOT NULL DEFAULT 0 COMMENT '已重试次数',
  `max_retries` INT NOT NULL DEFAULT 3 COMMENT '最大重试次数',
  `started_at` DATETIME DEFAULT NULL COMMENT '开始执行时间',
  `completed_at` DATETIME DEFAULT NULL COMMENT '完成时间',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `ix_pipeline_tasks_poll` (`status`, `priority`, `created_at`),
  KEY `ix_pipeline_tasks_stage` (`stage`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='流水线任务队列表';

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
('report:generate', 'report', 'generate', 'Generate reports'),
-- 每日报告权限
('daily_report:read', 'daily_report', 'read', 'View daily reports'),
('daily_report:generate', 'daily_report', 'generate', 'Generate daily reports'),
('daily_report:export', 'daily_report', 'export', 'Export daily reports'),
-- 跨服务器同步权限
('sync:manual', 'sync', 'manual', 'Manually trigger cross-server sync');

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
    'report:read', 'report:generate',
    'daily_report:read', 'daily_report:generate', 'daily_report:export',
    'sync:manual'
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
    'report:read', 'report:generate',
    'daily_report:read'
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
INSERT INTO `arxiv_categories` (`code`, `name`, `name_zh`, `parent_code`, `is_active`) VALUES
-- Computer Science - AI 相关分类（默认激活）
('cs.LG', 'Machine Learning', '机器学习', 'Computer Science', 1),
('cs.CV', 'Computer Vision and Pattern Recognition', '计算机视觉', 'Computer Science', 1),
('cs.CL', 'Computation and Language', '计算与语言', 'Computer Science', 1),
('cs.IR', 'Information Retrieval', '信息检索', 'Computer Science', 1),
('cs.AI', 'Artificial Intelligence', '人工智能', 'Computer Science', 1),
('cs.NE', 'Neural and Evolutionary Computing', '神经网络与计算', 'Computer Science', 1),
-- Computer Science - 其他分类（默认不激活）
('cs.DC', 'Distributed, Parallel, and Cluster Computing', '分布式计算', 'Computer Science', 0),
('cs.RO', 'Robotics', '机器人', 'Computer Science', 0),
('cs.SE', 'Software Engineering', '软件工程', 'Computer Science', 0),
('cs.DB', 'Databases', '数据库', 'Computer Science', 0),
('cs.NI', 'Networking and Internet Architecture', '网络与互联网', 'Computer Science', 0),
('cs.CR', 'Cryptography and Security', '密码学与安全', 'Computer Science', 0),
('cs.HC', 'Human-Computer Interaction', '人机交互', 'Computer Science', 0),
('cs.IT', 'Information Theory', '信息论', 'Computer Science', 0),
('cs.CY', 'Computers and Society', '计算机与社会', 'Computer Science', 0),
('cs.AR', 'Hardware Architecture', '硬件架构', 'Computer Science', 0),
('cs.CG', 'Computational Geometry', '计算几何', 'Computer Science', 0),
('cs.FL', 'Formal Languages and Automata Theory', '形式语言与自动机', 'Computer Science', 0),
('cs.DS', 'Data Structures and Algorithms', '数据结构与算法', 'Computer Science', 0),
('cs.CC', 'Computational Complexity', '计算复杂性', 'Computer Science', 0),
('cs.DL', 'Digital Libraries', '数字图书馆', 'Computer Science', 0),
('cs.LO', 'Logic in Computer Science', '计算机逻辑', 'Computer Science', 0),
('cs.MA', 'Multiagent Systems', '多智能体系统', 'Computer Science', 0),
('cs.MM', 'Multimedia', '多媒体', 'Computer Science', 0),
('cs.OS', 'Operating Systems', '操作系统', 'Computer Science', 0),
('cs.PF', 'Performance', '性能', 'Computer Science', 0),
('cs.PL', 'Programming Languages', '编程语言', 'Computer Science', 0),
('cs.ET', 'Emerging Technologies', '新兴技术', 'Computer Science', 0),
('cs.GR', 'Graphics', '图形学', 'Computer Science', 0),
('cs.GT', 'Computer Science and Game Theory', '计算机博弈论', 'Computer Science', 0),
('cs.MS', 'Mathematical Software', '数学软件', 'Computer Science', 0),
('cs.NA', 'Numerical Analysis', '数值分析', 'Computer Science', 0),
('cs.OH', 'Other Computer Science', '其他计算机科学', 'Computer Science', 0),
('cs.SI', 'Social and Information Networks', '社会与信息网络', 'Computer Science', 0),
('cs.SD', 'Sound', '音频处理', 'Computer Science', 0),
('cs.SC', 'Symbolic Computation', '符号计算', 'Computer Science', 0),
('cs.SY', 'Systems and Control', '系统与控制', 'Computer Science', 0),
('cs.CE', 'Computational Engineering, Finance, and Science', '计算工程、金融与科学', 'Computer Science', 0),
-- Mathematics（默认不激活）
('math.AG', 'Algebraic Geometry', '代数几何', 'Mathematics', 0),
('math.AT', 'Algebraic Topology', '代数拓扑', 'Mathematics', 0),
('math.AP', 'Analysis of PDEs', '偏微分方程分析', 'Mathematics', 0),
('math.CA', 'Classical Analysis and ODEs', '经典分析与常微分方程', 'Mathematics', 0),
('math.CT', 'Category Theory', '范畴论', 'Mathematics', 0),
('math.CO', 'Combinatorics', '组合数学', 'Mathematics', 0),
('math.AC', 'Commutative Algebra', '交换代数', 'Mathematics', 0),
('math.CV', 'Complex Variables', '复变函数', 'Mathematics', 0),
('math.DG', 'Differential Geometry', '微分几何', 'Mathematics', 0),
('math.DS', 'Dynamical Systems', '动力系统', 'Mathematics', 0),
('math.FA', 'Functional Analysis', '泛函分析', 'Mathematics', 0),
('math.GM', 'General Mathematics', '一般数学', 'Mathematics', 0),
('math.GN', 'General Topology', '一般拓扑', 'Mathematics', 0),
('math.GT', 'Geometric Topology', '几何拓扑', 'Mathematics', 0),
('math.GR', 'Group Theory', '群论', 'Mathematics', 0),
('math.HO', 'History and Overview', '数学史与概述', 'Mathematics', 0),
('math.IT', 'Information Theory', '信息论', 'Mathematics', 0),
('math.KT', 'K-Theory and Homology', 'K理论与同调', 'Mathematics', 0),
('math.LO', 'Logic', '数理逻辑', 'Mathematics', 0),
('math.MP', 'Mathematical Physics', '数学物理', 'Mathematics', 0),
('math.MG', 'Metric Geometry', '度量几何', 'Mathematics', 0),
('math.NT', 'Number Theory', '数论', 'Mathematics', 0),
('math.NA', 'Numerical Analysis', '数值分析', 'Mathematics', 0),
('math.OC', 'Optimization and Control', '最优化与控制', 'Mathematics', 0),
('math.OA', 'Operator Algebras', '算子代数', 'Mathematics', 0),
('math.PR', 'Probability', '概率论', 'Mathematics', 0),
('math.QA', 'Quantum Algebra', '量子代数', 'Mathematics', 0),
('math.RT', 'Representation Theory', '表示论', 'Mathematics', 0),
('math.RA', 'Rings and Algebras', '环与代数', 'Mathematics', 0),
('math.SP', 'Spectral Theory', '谱理论', 'Mathematics', 0),
('math.ST', 'Statistics Theory', '统计理论', 'Mathematics', 0),
('math.SG', 'Symplectic Geometry', '辛几何', 'Mathematics', 0),
-- Physics - Astrophysics（默认不激活）
('astro-ph.CO', 'Cosmology and Nongalactic Astrophysics', '宇宙学与河外天体物理', 'Physics', 0),
('astro-ph.EP', 'Earth and Planetary Astrophysics', '地球与行星天体物理', 'Physics', 0),
('astro-ph.GA', 'Astrophysics of Galaxies', '星系天体物理', 'Physics', 0),
('astro-ph.HE', 'High Energy Astrophysical Phenomena', '高能天体物理', 'Physics', 0),
('astro-ph.IM', 'Instrumentation and Methods for Astrophysics', '天体物理仪器与方法', 'Physics', 0),
('astro-ph.SR', 'Solar and Stellar Astrophysics', '太阳与恒星天体物理', 'Physics', 0),
-- Physics - Condensed Matter（默认不激活）
('cond-mat.dis-nn', 'Disordered Systems and Neural Networks', '无序系统与神经网络', 'Physics', 0),
('cond-mat.mes-hall', 'Mesoscale and Nanoscale Physics', '介观与纳米物理', 'Physics', 0),
('cond-mat.mtrl-sci', 'Materials Science', '材料科学', 'Physics', 0),
('cond-mat.other', 'Other Condensed Matter', '其他凝聚态物理', 'Physics', 0),
('cond-mat.quant-gas', 'Quantum Gases', '量子气体', 'Physics', 0),
('cond-mat.soft', 'Soft Condensed Matter', '软凝聚态物理', 'Physics', 0),
('cond-mat.stat-mech', 'Statistical Mechanics', '统计力学', 'Physics', 0),
('cond-mat.str-el', 'Strongly Correlated Electrons', '强关联电子', 'Physics', 0),
('cond-mat.supr-con', 'Superconductivity', '超导', 'Physics', 0),
-- Physics - Other（默认不激活）
('gr-qc', 'General Relativity and Quantum Cosmology', '广义相对论与量子宇宙学', 'Physics', 0),
('hep-ex', 'High Energy Physics - Experiment', '高能物理实验', 'Physics', 0),
('hep-lat', 'High Energy Physics - Lattice', '高能物理格点', 'Physics', 0),
('hep-ph', 'High Energy Physics - Phenomenology', '高能物理唯象学', 'Physics', 0),
('hep-th', 'High Energy Physics - Theory', '高能物理理论', 'Physics', 0),
('math-ph', 'Mathematical Physics', '数学物理', 'Physics', 0),
('nlin.AO', 'Adaptation and Self-Organizing Systems', '适应与自组织系统', 'Physics', 0),
('nlin.CD', 'Chaotic Dynamics', '混沌动力学', 'Physics', 0),
('nlin.CG', 'Cellular Automata and Lattice Gases', '细胞自动机与格气', 'Physics', 0),
('nlin.PS', 'Pattern Formation and Solitons', '模式形成与孤子', 'Physics', 0),
('nlin.SI', 'Exactly Solvable and Integrable Systems', '可积系统', 'Physics', 0),
('nucl-ex', 'Nuclear Experiment', '核物理实验', 'Physics', 0),
('nucl-th', 'Nuclear Theory', '核物理理论', 'Physics', 0),
('physics.acc-ph', 'Accelerator Physics', '加速器物理', 'Physics', 0),
('physics.ao-ph', 'Atmospheric and Oceanic Physics', '大气与海洋物理', 'Physics', 0),
('physics.app-ph', 'Applied Physics', '应用物理', 'Physics', 0),
('physics.atm-clus', 'Atomic and Molecular Clusters', '原子与分子团簇', 'Physics', 0),
('physics.atom-ph', 'Atomic Physics', '原子物理', 'Physics', 0),
('physics.bio-ph', 'Biological Physics', '生物物理', 'Physics', 0),
('physics.chem-ph', 'Chemical Physics', '化学物理', 'Physics', 0),
('physics.class-ph', 'Classical Physics', '经典物理', 'Physics', 0),
('physics.data-an', 'Data Analysis, Statistics and Probability', '数据分析与统计', 'Physics', 0),
('physics.ed-ph', 'Physics Education', '物理教育', 'Physics', 0),
('physics.flu-dyn', 'Fluid Dynamics', '流体力学', 'Physics', 0),
('physics.gen-ph', 'General Physics', '普通物理', 'Physics', 0),
('physics.geo-ph', 'Geophysics', '地球物理', 'Physics', 0),
('physics.hist-ph', 'History and Philosophy of Physics', '物理学史与哲学', 'Physics', 0),
('physics.ins-det', 'Instrumentation and Detectors', '仪器与探测器', 'Physics', 0),
('physics.med-ph', 'Medical Physics', '医学物理', 'Physics', 0),
('physics.optics', 'Optics', '光学', 'Physics', 0),
('physics.plasm-ph', 'Plasma Physics', '等离子体物理', 'Physics', 0),
('physics.pop-ph', 'Popular Physics', '科普物理', 'Physics', 0),
('physics.soc-ph', 'Physics and Society', '物理与社会', 'Physics', 0),
('physics.space-ph', 'Space Physics', '空间物理', 'Physics', 0),
('quant-ph', 'Quantum Physics', '量子物理', 'Physics', 0),
('physics.comp-ph', 'Computational Physics', '计算物理', 'Physics', 0),
-- Statistics（默认不激活）
('stat.AP', 'Applications', '统计应用', 'Statistics', 0),
('stat.CO', 'Computation', '统计计算', 'Statistics', 0),
('stat.ME', 'Methodology', '统计方法', 'Statistics', 0),
('stat.TH', 'Statistics Theory', '统计理论', 'Statistics', 0),
('stat.OT', 'Other Statistics', '其他统计', 'Statistics', 0),
('stat.ML', 'Machine Learning', '机器学习', 'Statistics', 0),
-- Electrical Engineering（默认不激活）
('eess.AS', 'Audio and Speech Processing', '音频与语音处理', 'Electrical Engineering', 0),
('eess.IV', 'Image and Video Processing', '图像与视频处理', 'Electrical Engineering', 0),
('eess.SP', 'Signal Processing', '信号处理', 'Electrical Engineering', 0),
('eess.SY', 'Systems and Control', '系统与控制', 'Electrical Engineering', 0),
-- Economics（默认不激活）
('econ.EM', 'Econometrics', '计量经济学', 'Economics', 0),
('econ.GN', 'General Economics', '一般经济学', 'Economics', 0),
('econ.TH', 'Theoretical Economics', '理论经济学', 'Economics', 0),
-- Quantitative Biology（默认不激活）
('q-bio.BM', 'Biomolecules', '生物分子', 'Quantitative Biology', 0),
('q-bio.CB', 'Cell Behavior', '细胞行为', 'Quantitative Biology', 0),
('q-bio.GN', 'Genomics', '基因组学', 'Quantitative Biology', 0),
('q-bio.MN', 'Molecular Networks', '分子网络', 'Quantitative Biology', 0),
('q-bio.NC', 'Neurons and Cognition', '神经元与认知', 'Quantitative Biology', 0),
('q-bio.OT', 'Other Quantitative Biology', '其他定量生物学', 'Quantitative Biology', 0),
('q-bio.PE', 'Populations and Evolution', '种群与进化', 'Quantitative Biology', 0),
('q-bio.SC', 'Subcellular Processes', '亚细胞过程', 'Quantitative Biology', 0),
('q-bio.TO', 'Tissues and Organs', '组织与器官', 'Quantitative Biology', 0),
('q-bio.QM', 'Quantitative Methods', '定量方法', 'Quantitative Biology', 0),
-- Quantitative Finance（默认不激活）
('q-fin.CP', 'Computational Finance', '计算金融', 'Quantitative Finance', 0),
('q-fin.EC', 'Economics', '经济学', 'Quantitative Finance', 0),
('q-fin.GN', 'General Finance', '一般金融', 'Quantitative Finance', 0),
('q-fin.MF', 'Mathematical Finance', '数理金融', 'Quantitative Finance', 0),
('q-fin.PM', 'Portfolio Management', '投资组合管理', 'Quantitative Finance', 0),
('q-fin.PR', 'Pricing of Securities', '证券定价', 'Quantitative Finance', 0),
('q-fin.RM', 'Risk Management', '风险管理', 'Quantitative Finance', 0),
('q-fin.ST', 'Statistical Finance', '统计金融', 'Quantitative Finance', 0),
('q-fin.TR', 'Trading and Market Microstructure', '交易与市场微观结构', 'Quantitative Finance', 0);

-- -----------------------------------------------------------------------------
-- 插入 RSS 订阅源数据
-- 注意: 只有以下源默认启用(is_active=1), 其他源保留但默认不抓取(is_active=0):
--   量子位、36氪资讯、虎嗅网、机器之心、美团技术团队
-- -----------------------------------------------------------------------------
INSERT INTO `rss_feeds` (`title`, `feed_url`, `site_url`, `category`, `description`, `is_active`, `country`, `news_category`) VALUES
-- 其他 (默认不抓取)
('The Guardian/World', 'https://www.theguardian.com/world/rss', '', '其他', '', 0, 'EN', 'general'),
('New Yorker: Culture', 'https://www.newyorker.com/feed/everything', '', '其他', '', 0, 'EN', 'general'),
('博海拾贝', 'https://bohaishibei.com/feed/', '', '其他', '', 0, 'CN', 'general'),
('The Atlantic', 'https://www.theatlantic.com/feed/all/', '', '其他', '', 0, 'EN', 'general'),
('中英文双语新闻 热词翻译- 中国日报21世纪英文报', 'http://www.chinadaily.com.cn/rss/china_rss.xml', '', '其他', '', 0, 'CN', 'general'),
('运营派', 'https://www.yunyingpai.com/feed', '', '其他', '', 0, 'CN', 'general'),
('TIME', 'http://feeds.feedburner.com/time/topstories', '', '其他', '', 0, 'EN', 'general'),
('The Washington Post', 'http://feeds.washingtonpost.com/rss/world', '', '其他', '', 0, 'EN', 'general'),
('最新更新 – Solidot', 'https://www.solidot.org/index.rss', '', '其他', '', 0, 'CN', 'tech'),
('量子位', 'https://www.qbitai.com/feed', '', '其他', '', 1, 'CN', 'tech'),
('36氪资讯 - 推荐', 'https://36kr.com/feed', '', '其他', '', 1, 'CN', 'tech'),
('掘金阅读 - rsshub', 'https://juejin.cn/rss', '', '其他', '', 0, 'CN', 'tech'),
('CNN/Business', 'http://rss.cnn.com/rss/edition.rss', '', '其他', '', 0, 'EN', 'general'),
('IT之家-24 小时最热', 'https://www.ithome.com/rss/', '', '其他', '', 0, 'CN', 'tech'),
('虎嗅网 - 首页资讯 - rsshub', 'https://www.huxiu.com/rss/0.xml', '', '其他', '', 1, 'CN', 'tech'),
('Nature Communications', 'http://feeds.nature.com/nature/rss/current', '', '其他', '', 0, NULL, NULL),
('热门文章 - 人人都是产品经理', 'http://www.woshipm.com/feed', '', '其他', '', 0, 'CN', 'general'),
('TechNews 科技新報', 'https://techcrunch.com/feed/', '', '其他', '', 0, 'EN', 'tech'),
('人民论坛评论_人民论坛网_中央重点理论网站_人民日报社主管', 'http://www.people.com.cn/rss/politics.xml', '', '其他', '', 0, 'CN', 'general'),
('时政频道_新华网', 'http://www.xinhuanet.com/politics/news_politics.xml', '', '其他', '', 0, 'CN', 'general'),
('文章 | 机核 GCORES - rsshub', 'https://www.gcores.com/rss', '', '其他', '', 0, NULL, NULL),
('WIRED / Tech', 'https://www.wired.com/feed/rss', '', '其他', '', 0, 'EN', 'tech'),
('Scientific American Content: Global', 'https://www.science.org/rss/news_current.xml', '', '其他', '', 0, 'EN', 'tech'),
('Top News - MIT Technology Review', 'https://www.technologyreview.com/feed/', '', '其他', '', 0, 'EN', 'tech'),
('NYT > World News', 'https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml', '', '其他', '', 0, 'EN', 'general'),
-- 科技 (默认不抓取)
('爱范儿', 'https://www.ifanr.com/feed', '', '科技', '', 0, 'CN', 'tech'),
('数字尾巴', 'https://www.dgtle.com/rss/dgtle.xml', '', '科技', '', 0, 'CN', 'tech'),
('小众软件', 'https://www.appinn.com/feed/', '', '科技', '', 0, 'CN', 'tech'),
('机器之心', 'https://www.jiqizhixin.com/rss', '', '科技', '', 1, 'CN', 'tech'),
('V2EX - 分享创造', 'https://www.v2ex.com/index.xml', '', '科技', '', 0, 'CN', 'tech'),
('钛媒体：引领未来商业与生活新知', 'https://www.tmtpost.com/rss.xml', '', '科技', '', 0, 'CN', 'tech'),
('异次元软件世界', 'https://www.iplaysoft.com/feed', '', '科技', '', 0, 'CN', 'tech'),
('小道消息', 'https://happyxiao.com/feed/', '', '科技', '', 0, 'CN', 'tech'),
-- 科学 (默认不抓取)
('cs.CV@arXiv.org', 'http://export.arxiv.org/rss/cs', '', '科学', '', 0, NULL, NULL),
-- 商业财经 (默认不抓取)
('经济观察报', 'http://www.eeo.com.cn/rss.xml', '', '商业财经', '', 0, 'EN', 'finance'),
-- 游戏 (默认不抓取)
('触乐', 'https://www.chuapp.com/feed', '', '游戏', '', 0, NULL, NULL),
('游研社', 'https://www.yystv.cn/rss/feed', '', '游戏', '', 0, NULL, NULL),
-- IT/软件开发 (默认不抓取)
('阮一峰的网络日志', 'https://www.ruanyifeng.com/blog/atom.xml', '', 'IT/软件开发', '', 0, NULL, NULL),
-- 科技新闻 (默认不抓取)
('New York Times Tech', 'https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml', '', '科技新闻', '', 0, 'EN', 'tech'),
('TechCrunch', 'https://techcrunch.com/feed', '', '科技新闻', '', 0, 'EN', 'tech'),
-- 开发者 (默认不抓取)
('GitHub Blog', 'https://github.blog/feed', '', '开发者', '', 0, NULL, NULL),
('Stack Overflow Blog', 'https://stackoverflow.blog/feed', '', '开发者', '', 0, NULL, NULL),
-- 生活 (默认不抓取)
('理想生活实验室', 'https://www.toodaylab.com/feed', '', '生活', '', 0, NULL, NULL),
('Lifehacker', 'https://lifehacker.com/rss', '', '生活', '', 0, NULL, NULL),
-- 读书/文化 (默认不抓取)
('扯氮集', 'http://weiwuhui.com/feed', '', '读书/文化', '', 0, NULL, NULL),
('海德沙龙（HeadSalon）', 'http://headsalon.org/feed', '', '读书/文化', '', 0, NULL, NULL),
-- 技术社区 (默认不抓取)
('Hacker News', 'https://news.ycombinator.com/rss', '', '技术社区', '', 0, NULL, NULL),
-- 消费科技 (默认不抓取)
('The Verge', 'https://www.theverge.com/rss/index.xml', '', '消费科技', '', 0, 'EN', 'tech'),
-- 新闻媒体 (默认不抓取)
('联合早报', 'https://plink.anyfeeder.com/zaobao/realtime/china', '', '新闻媒体', '', 0, 'EN', 'general'),
-- 前沿科技 (默认不抓取)
('MIT Technology Review', 'https://www.technologyreview.com/feed', '', '前沿科技', '', 0, 'EN', 'tech'),
-- 技术与社会 (默认不抓取)
('编程随想的博客', 'https://feeds2.feedburner.com/programthink', '', '技术与社会', '', 0, NULL, NULL),
-- 设计与开发 (默认不抓取)
('Smashing Magazine', 'https://www.smashingmagazine.com/feed', '', '设计与开发', '', 0, NULL, NULL),
-- 效率工具 (默认不抓取)
('少数派', 'https://sspai.com/feed', '', '效率工具', '', 0, NULL, NULL),
-- IT专业 (默认不抓取)
('TechRepublic', 'https://www.techrepublic.com/rssfeeds/articles', '', 'IT专业', '', 0, NULL, NULL),
-- 前端开发 (默认不抓取)
('CSS-Tricks', 'https://css-tricks.com/feed', '', '前端开发', '', 0, NULL, NULL),
-- 技术博客 (默认不抓取)
('酷壳 CoolShell', 'https://coolshell.cn/feed', '', '技术博客', '', 0, NULL, NULL),
-- 网页设计 (默认不抓取)
('A List Apart', 'https://alistapart.com/main/feed', '', '网页设计', '', 0, NULL, NULL),
-- 互联网 (默认不抓取)
('月光博客', 'https://www.williamlong.info/rss.xml', '', '互联网', '', 0, NULL, NULL),
-- 技术团队
('美团技术团队', 'https://tech.meituan.com/feed', '', '技术团队', '', 1, NULL, NULL),
('DevOps.com', 'https://devops.com/feed/', 'https://devops.com', 'DevOps', '', 0, NULL, NULL),
('AWS Blog', 'https://aws.amazon.com/blogs/aws/feed/', 'https://aws.amazon.com', '云计算', '', 0, NULL, NULL),
('Google Cloud Blog', 'https://cloud.google.com/blog/feed', 'https://cloud.google.com', '云计算', '', 0, NULL, NULL),
('Azure Blog', 'https://azure.microsoft.com/en-us/blog/feed/', 'https://azure.microsoft.com', '云计算', '', 0, NULL, NULL),
('r/MachineLearning', 'https://www.reddit.com/r/MachineLearning/.rss', 'https://www.reddit.com', '人工智能', '', 0, NULL, NULL),
('Distill', 'http://distill.pub/rss.xml', 'http://distill.pub', '人工智能', '', 0, NULL, NULL),
('Product Hunt', 'https://www.producthunt.com/feed', 'https://www.producthunt.com', '创业', '', 0, NULL, NULL),
('VentureBeat', 'https://feeds.feedburner.com/venturebeat/SZYF', 'https://feeds.feedburner.com', '创业', '', 0, NULL, NULL),
('AVC', 'https://avc.com/feed/', 'https://avc.com', '创业', '', 0, NULL, NULL),
('CSS-Tricks', 'https://css-tricks.com/feed/', 'https://css-tricks.com', '前端开发', '', 0, NULL, NULL),
('Mozilla Hacks', 'https://hacks.mozilla.org/feed/', 'https://hacks.mozilla.org', '前端开发', '', 0, NULL, NULL),
('CoinDesk', 'https://www.coindesk.com/arc/outboundfeeds/rss/', 'https://www.coindesk.com', '区块链', '', 0, NULL, NULL),
('Bloomberg', 'https://www.bloomberg.com/feed/podcast/bloomberg-technology.xml', 'https://www.bloomberg.com', '商业财经', '', 0, 'EN', 'finance'),
('Forbes Business', 'https://www.forbes.com/business/feed/', 'https://www.forbes.com', '商业财经', '', 0, 'EN', 'finance'),
('Fortune', 'https://fortune.com/feed', 'https://fortune.com', '商业财经', '', 0, 'EN', 'finance'),
('HBR IdeaCast', 'http://feeds.harvardbusiness.org/harvardbusiness/ideacast', 'http://feeds.harvardbusiness.org', '商业财经', '', 0, 'EN', 'finance'),
('BBC News World', 'http://feeds.bbci.co.uk/news/world/rss.xml', 'http://feeds.bbci.co.uk', '国际新闻', '', 0, 'EN', 'general'),
('CNN World', 'http://rss.cnn.com/rss/edition_world.rss', 'http://rss.cnn.com', '国际新闻', '', 0, 'EN', 'general'),
('Reuters World', 'https://www.reuters.com/rssFeed/worldNews', 'https://www.reuters.com', '国际新闻', '', 0, 'EN', 'general'),
-- 中国新闻网（央媒综合新闻）
('中国新闻网-滚动新闻', 'https://www.chinanews.com.cn/rss/scroll-news.xml', 'https://www.chinanews.com.cn', '央媒综合', '中国新闻网滚动新闻', 1, 'CN', 'general'),
('中国新闻网-要闻导读', 'https://www.chinanews.com.cn/rss/importnews.xml', 'https://www.chinanews.com.cn', '央媒综合', '中国新闻网要闻导读', 1, 'CN', 'general'),
('中国新闻网-时政新闻', 'https://www.chinanews.com.cn/rss/china.xml', 'https://www.chinanews.com.cn', '央媒综合', '中国新闻网时政新闻', 1, 'CN', 'general'),
('中国新闻网-国际新闻', 'https://www.chinanews.com.cn/rss/world.xml', 'https://www.chinanews.com.cn', '央媒综合', '中国新闻网国际新闻', 1, 'CN', 'general'),
('中国新闻网-社会新闻', 'https://www.chinanews.com.cn/rss/society.xml', 'https://www.chinanews.com.cn', '央媒综合', '中国新闻网社会新闻', 1, 'CN', 'general'),
-- 虎嗅网全站（与已有 /0.xml 首页资讯互补）
('虎嗅网-全站', 'https://www.huxiu.com/rss/1.xml', 'https://www.huxiu.com', '科技', '虎嗅网全站资讯', 0, 'CN', 'tech'),
('GitHub Blog', 'https://github.blog/feed/', 'https://github.blog', '开发者', '', 0, NULL, NULL),
('Stack Overflow Blog', 'https://stackoverflow.blog/feed/', 'https://stackoverflow.blog', '开发者', '', 0, NULL, NULL),
('GitHub Trending', 'https://mshibanami.github.io/github-trending-feed.xml', 'https://mshibanami.github.io', '开源', '', 0, NULL, NULL),
('Variety', 'https://variety.com/feed/', 'https://variety.com', '影视', '', 0, NULL, NULL),
('IndieWire', 'https://www.indiewire.com/feed', 'https://www.indiewire.com', '影视', '', 0, NULL, NULL),
('Deadline', 'https://deadline.com/feed/', 'https://deadline.com', '影视', '', 0, NULL, NULL),
('Coding Horror', 'https://feeds.feedburner.com/codinghorror', 'https://feeds.feedburner.com', '技术博客', '', 0, NULL, NULL),
-- 矩阵67（技术博客，已验证有效 RSS）
('矩阵67', 'https://matrix67.com/blog/feed/', 'https://matrix67.com', '技术博客', '矩阵67-探索数学之美', 0, 'CN', 'tech'),
-- 知乎日报（通过 RSSHub，连接不稳定，默认不启用）
('知乎日报', 'https://rsshub.app/zhihu/daily', 'https://daily.zhihu.com', '综合', '知乎日报精选', 0, 'CN', 'general'),
('Martin Fowler', 'https://martinfowler.com/feed.atom', 'https://martinfowler.com', '技术博客', '', 0, NULL, NULL),
('Netflix TechBlog', 'https://netflixtechblog.com/feed', 'https://netflixtechblog.com', '技术团队', '', 0, NULL, NULL),
('HackerNoon', 'https://medium.com/feed/hackernoon', 'https://medium.com', '技术社区', '', 0, NULL, NULL),
('Investing.com', 'https://www.investing.com/rss/news.rss', 'https://www.investing.com', '投资理财', '', 0, NULL, NULL),
-- === 高质量技术博客（来自 worth-reading 列表）===
-- Tech Company Blogs
('Airbnb Engineering', 'https://medium.com/feed/airbnb-engineering', 'https://medium.com/airbnb-engineering', '技术团队', 'Airbnb Engineering Blog', 0, 'EN', 'tech'),
('Allegro.tech', 'https://blog.allegro.tech/feed.xml', 'https://blog.allegro.tech', '技术团队', 'Allegro Engineering Blog', 0, 'EN', 'tech'),
('Cloudflare Blog', 'https://blog.cloudflare.com/rss/', 'https://blog.cloudflare.com', '技术团队', 'Cloudflare Engineering Blog', 0, 'EN', 'tech'),
('Dropbox Tech Blog', 'https://dropbox.tech/feed', 'https://dropbox.tech', '技术团队', 'Dropbox Tech Blog', 0, 'EN', 'tech'),
('GitHub Engineering', 'https://github.blog/engineering/feed/', 'https://github.blog/engineering', '技术团队', 'GitHub Engineering Blog', 0, 'EN', 'tech'),
('Google Research Blog', 'https://research.google/blog/rss/', 'https://research.google/blog', '研究机构', 'Google Research Blog', 0, 'EN', 'tech'),
('Hugging Face Blog', 'https://huggingface.co/blog/feed.xml', 'https://huggingface.co/blog', 'AI/ML', 'Hugging Face Blog', 0, 'EN', 'tech'),
('Microsoft Research Blog', 'https://www.microsoft.com/en-us/research/feed/', 'https://www.microsoft.com/en-us/research', '研究机构', 'Microsoft Research Blog', 0, 'EN', 'tech'),
('Pinterest Engineering', 'https://medium.com/feed/pinterest-engineering', 'https://medium.com/pinterest-engineering', '技术团队', 'Pinterest Engineering Blog', 0, 'EN', 'tech'),
('Slack Engineering', 'https://slack.engineering/feed', 'https://slack.engineering', '技术团队', 'Slack Engineering Blog', 0, 'EN', 'tech'),
('Spotify Engineering', 'https://engineering.atspotify.com/feed', 'https://engineering.atspotify.com', '技术团队', 'Spotify Engineering Blog', 0, 'EN', 'tech'),
('Stripe Engineering', 'https://stripe.com/blog/feed.rss', 'https://stripe.com/blog', '技术团队', 'Stripe Engineering Blog', 0, 'EN', 'tech'),
('The Software House', 'https://effectivedelivery.io/feed.xml', 'https://effectivedelivery.io', '技术团队', 'The Software House Blog', 0, 'EN', 'tech'),
-- Personal Blogs
('Addy Osmani', 'https://addyosmani.com/rss.xml', 'https://addyosmani.com', '技术博客', 'Addy Osmani Blog', 0, 'EN', 'tech'),
('Adrian Roselli', 'https://adrianroselli.com/feed', 'https://adrianroselli.com', '技术博客', 'Adrian Roselli Blog', 0, 'EN', 'tech'),
('Ahmad Shadeed', 'https://ishadeed.com/feed.xml', 'https://ishadeed.com', '技术博客', 'Ahmad Shadeed Blog', 0, 'EN', 'tech'),
('Alex MacArthur', 'https://macarthur.me/rss/feed.xml', 'https://macarthur.me', '技术博客', 'Alex MacArthur Blog', 0, 'EN', 'tech'),
('Boris Tane', 'https://boristane.com/rss.xml', 'https://boristane.com', '技术博客', 'Boris Tane Blog', 0, 'EN', 'tech'),
('Dr. Axel Rauschmayer', 'https://2ality.com/feeds/posts.atom', 'https://2ality.com', '技术博客', '2ality - JavaScript Blog', 0, 'EN', 'tech'),
('Dries Buytaert', 'https://dri.es/rss.xml', 'https://dri.es', '技术博客', 'Dries Buytaert Blog', 0, 'EN', 'tech'),
('Guillaume Plique (Vjeux)', 'https://blog.vjeux.com/feed', 'https://blog.vjeux.com', '技术博客', 'Vjeux Blog', 0, 'EN', 'tech'),
('Josh W. Comeau', 'https://www.joshwcomeau.com/rss.xml', 'https://www.joshwcomeau.com', '技术博客', 'Josh W. Comeau Blog', 0, 'EN', 'tech'),
('Matt Smith', 'https://allthingssmitty.com/atom.xml', 'https://allthingssmitty.com', '技术博客', 'AllThingsSmitty Blog', 0, 'EN', 'tech'),
('Oskar Dudycz', 'https://www.architecture-weekly.com/feed.xml', 'https://www.architecture-weekly.com', '技术博客', 'Architecture Weekly', 0, 'EN', 'tech'),
('Remy Sharp', 'https://remysharp.com/blog.xml', 'https://remysharp.com', '技术博客', 'Remy Sharp Blog', 0, 'EN', 'tech'),
('Simon Willison', 'https://simonwillison.net/atom/entries/', 'https://simonwillison.net', '技术博客', 'Simon Willison Blog', 0, 'EN', 'tech'),
('Yan Cui', 'https://theburningmonk.com/feed/', 'https://theburningmonk.com', '技术博客', 'The Burning Monk Blog', 0, 'EN', 'tech'),
-- Polish Blogs
('aifullstack.pl', 'https://aifullstack.pl/rss.xml', 'https://aifullstack.pl', '技术博客', 'AI Fullstack (Polish)', 0, 'PL', 'tech'),
('Informatyk Zakładowy', 'https://informatykzakladowy.pl/feed', 'https://informatykzakladowy.pl', '技术博客', 'Informatyk Zakładowy (Polish)', 0, 'PL', 'tech'),
('Niebezpiecznik', 'https://feeds.feedburner.com/niebezpiecznik', 'https://niebezpiecznik.pl', '安全', 'Niebezpiecznik (Polish Security)', 0, 'PL', 'tech'),
('Sekurak', 'https://sekurak.pl/feed', 'https://sekurak.pl', '安全', 'Sekurak (Polish Security)', 0, 'PL', 'tech'),
('Yahoo Finance', 'https://finance.yahoo.com/news/rssindex', 'https://finance.yahoo.com', '投资理财', '', 0, NULL, NULL),
('The Daily (NYT)', 'https://feeds.simplecast.com/54nAGcIl', 'https://feeds.simplecast.com', '播客', '', 0, NULL, NULL),
('Lex Fridman', 'https://lexfridman.com/feed/', 'https://lexfridman.com', '播客', '', 0, NULL, NULL),
('Towards Data Science', 'https://towardsdatascience.com/feed', 'https://towardsdatascience.com', '数据科学', '', 0, NULL, NULL),
('Japan Times', 'https://www.japantimes.co.jp/feed/topstories/', 'https://www.japantimes.co.jp', '日本新闻', '', 0, 'EN', 'general'),
('Japan Today', 'https://japantoday.com/feed', 'https://japantoday.com', '日本新闻', '', 0, 'EN', 'general'),
('IGN', 'http://feeds.ign.com/ign/all', 'http://feeds.ign.com', '游戏', '', 0, NULL, NULL),
('Kotaku', 'https://kotaku.com/rss', 'https://kotaku.com', '游戏', '', 0, NULL, NULL),
('Polygon', 'https://www.polygon.com/rss/index.xml', 'https://www.polygon.com', '游戏', '', 0, NULL, NULL),
('GameSpot', 'https://www.gamespot.com/feeds/mashup/', 'https://www.gamespot.com', '游戏', '', 0, NULL, NULL),
('Steam News', 'https://store.steampowered.com/feeds/news.xml', 'https://store.steampowered.com', '游戏', '', 0, NULL, NULL),
('Nature', 'https://www.nature.com/nature.rss', 'https://www.nature.com', '科学', '', 0, NULL, NULL),
('ScienceDaily', 'https://www.sciencedaily.com/rss/all.xml', 'https://www.sciencedaily.com', '科学', '', 0, NULL, NULL),
('TechCrunch', 'http://feeds.feedburner.com/TechCrunch', 'http://feeds.feedburner.com', '科技新闻', '', 0, 'EN', 'tech'),
('Ars Technica', 'http://feeds.arstechnica.com/arstechnica/index', 'http://feeds.arstechnica.com', '科技新闻', '', 0, 'EN', 'tech'),
('Engadget', 'https://www.engadget.com/rss.xml', 'https://www.engadget.com', '科技新闻', '', 0, 'EN', 'tech'),
('Gizmodo', 'https://gizmodo.com/rss', 'https://gizmodo.com', '科技新闻', '', 0, 'EN', 'tech'),
('Android Developers Blog', 'http://feeds.feedburner.com/blogspot/hsDu', 'http://feeds.feedburner.com', '移动开发', '', 0, NULL, NULL),
('Android Weekly', 'https://us2.campaign-archive.com/feed?u=887caf4f48db76fd91e20a06d&id=4eb677ad19', 'https://us2.campaign-archive.com', '移动开发', '', 0, NULL, NULL),
('Swift by Sundell', 'https://www.swiftbysundell.com/feed.rss', 'https://www.swiftbysundell.com', '移动开发', '', 0, NULL, NULL),
('Apple Developer News', 'https://developer.apple.com/news/rss/news.rss', 'https://developer.apple.com', '移动开发', '', 0, NULL, NULL),
('Kotlin Blog', 'https://blog.jetbrains.com/kotlin/feed/', 'https://blog.jetbrains.com', '编程语言', '', 0, NULL, NULL),
('Krebs on Security', 'https://krebsonsecurity.com/feed/', 'https://krebsonsecurity.com', '网络安全', '', 0, NULL, NULL),
('Schneier on Security', 'https://www.schneier.com/feed/', 'https://www.schneier.com', '网络安全', '', 0, NULL, NULL),
('A List Apart', 'https://alistapart.com/main/feed/', 'https://alistapart.com', '网页设计', '', 0, NULL, NULL),
('WSJ World', 'https://feeds.a.dj.com/rss/RSSWorldNews.xml', 'https://feeds.a.dj.com', '美国新闻', '', 0, 'EN', 'general'),
('NASA Breaking News', 'https://www.nasa.gov/rss/dyn/breaking_news.rss', 'https://www.nasa.gov', '航空航天', '', 0, NULL, NULL),
('SpaceX', 'https://www.youtube.com/feeds/videos.xml?user=spacexchannel', 'https://www.youtube.com', '航空航天', '', 0, NULL, NULL),
('UX Collective', 'https://uxdesign.cc/feed', 'https://uxdesign.cc', '设计', '', 0, NULL, NULL),
('Designer News', 'https://www.designernews.co/?format=rss', 'https://www.designernews.co', '设计', '', 0, NULL, NULL),
('Book Riot', 'https://bookriot.com/feed/', 'https://bookriot.com', '读书', '', 0, NULL, NULL),
('Kirkus Reviews', 'https://www.kirkusreviews.com/feeds/rss/', 'https://www.kirkusreviews.com', '读书', '', 0, NULL, NULL),
('Pitchfork', 'http://pitchfork.com/rss/news', 'http://pitchfork.com', '音乐', '', 0, NULL, NULL),
('Billboard', 'https://www.billboard.com/articles/rss.xml', 'https://www.billboard.com', '音乐', '', 0, NULL, NULL),
('Hong Kong Free Press', 'https://www.hongkongfp.com/feed/', 'https://www.hongkongfp.com', '香港新闻', '', 0, 'EN', 'general'),
('South China Morning Post', 'https://www.scmp.com/rss/91/feed', 'https://www.scmp.com', '香港新闻', '', 0, 'EN', 'general'),
('Google News US', 'https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en', 'https://news.google.com', 'en_news', '', 0, 'EN', 'general');

-- -----------------------------------------------------------------------------
-- 插入 news_sources 种子数据（中文官方媒体 HTML 源）
-- 注意: selectors JSON 从 scripts/seed_news_sources.py 中的 CN_NEWS_SOURCES 取值
-- -----------------------------------------------------------------------------
INSERT INTO `news_sources` (`name`, `list_url`, `site_url`, `selectors`, `country`, `news_category`, `encoding`, `is_active`) VALUES
('新华网-时政', 'http://www.news.cn/politics/', 'http://www.xinhuanet.com',
 '{"article_list": "div.parts ul li", "title": "a", "link": "a", "summary": "p", "time": "span.time", "image": "img", "content": "div#detail"}',
 'CN', 'general', 'utf-8', 1),
('人民网-国内', 'http://www.people.com.cn/GB/59476/index.html', 'http://www.people.com.cn',
 '{"article_list": "div.ej_list_box ul li", "title": "a", "link": "a", "summary": "", "time": "em", "image": "img", "content": "div.rm_txt_con"}',
 'CN', 'general', 'gbk', 1),
('央视网-新闻', 'https://news.cctv.com/china/', 'https://news.cctv.com',
 '{"article_list": "div.text_list ul li", "title": "a", "link": "a", "summary": "p", "time": "span.time", "image": "img", "content": "div.cnt_bd"}',
 'CN', 'general', 'utf-8', 1);

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
('ai.ollama_api_key', '', 'Ollama API key (optional, for authenticated deployments)', 1),
('ai.openai_base_url', 'https://api.openai.com/v1', 'OpenAI API base URL (supports custom proxies or compatible APIs)', 0),
('ai.openai_model', 'gpt-4o', 'OpenAI model name', 0),
('ai.openai_model_light', 'gpt-4o-mini', 'OpenAI light model name', 0),
('ai.openai_timeout', '60', 'OpenAI request timeout in seconds', 0),
('ai.claude_model', 'claude-sonnet-4-20250514', 'Claude model name', 0),
('ai.claude_model_light', 'claude-haiku-4-20250514', 'Claude light model name', 0),
('ai.claude_timeout', '60', 'Claude request timeout in seconds', 0),
('ai.translate_max_tokens', '4096', 'Max output tokens for translation', 0),
('ai.cache_enabled', 'true', 'Enable AI result caching', 0),
('ai.cache_ttl', '86400', 'AI cache TTL in seconds', 0),
('ai.max_content_length', '1500', 'Max content length for AI processing', 0),
('ai.max_title_length', '200', 'Max title length for AI processing', 0),
('ai.thinking_enabled', 'false', 'Enable extended thinking mode', 0),
('ai.concurrent_enabled', 'false', 'Enable concurrent AI processing', 0),
('ai.workers_heavy', '2', 'Number of workers for heavy AI tasks', 0),
('ai.workers_screen', '4', 'Number of workers for screening tasks', 0),
('ai.no_think', 'false', 'Disable model thinking (qwen3, o1/o3 etc.)', 0),
('ai.num_predict', '512', 'Max generation tokens for high-value content', 0),
('ai.num_predict_simple', '256', 'Max generation tokens for simple tasks', 0),
('ai.max_retries', '3', 'Max retry attempts for AI API calls', 0),
('ai.retry_base_delay', '1.0', 'Retry base delay seconds (exponential backoff)', 0),
('ai.batch_concurrency', '1', 'Batch concurrency (1=serial)', 0),
('ai.fallback_provider', '', 'Fallback AI provider', 0),
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
('feature.translate', 'true', 'Title translation (auto-called during AI processing)', 0),
('feature.embedding', 'false', 'Embedding / Milvus', 0),
('feature.event_clustering', 'false', 'Event clustering', 0),
('feature.topic_radar', 'false', 'Topic radar', 0),
('feature.topic_match', 'false', 'Topic match (article-topic association)', 0),
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
('scheduler.topic_match_interval_hours', '2', 'Topic match interval in hours', 0),
('scheduler.topic_match_base_hour', '0', 'Topic match job base hour (0-23) for interval calculation', 0),
('scheduler.topic_match_days', '7', 'Topic match lookback days', 0),
('scheduler.topic_match_limit', '500', 'Topic match batch limit per run', 0),
('scheduler.backup_hour', '4', 'Hour of day to run backup (0-23)', 0),
('scheduler.cleanup_hour', '3', 'Hour of day to run cleanup (0-23)', 0),
('scheduler.action_extract_interval_hours', '2', 'Action item extraction interval in hours', 0),
('scheduler.report_weekly_day', 'mon', 'Day of week for weekly report generation', 0),
('scheduler.report_weekly_hour', '6', 'Hour of day for weekly report generation (0-23)', 0),
('scheduler.report_monthly_hour', '7', 'Hour of day for monthly report generation on 1st (0-23)', 0),
('scheduler.notification_hour', '9', 'Hour of day to send notification emails (0-23)', 0),
('scheduler.notification_minute', '0', 'Minute of hour to send notification emails (0-59)', 0),
-- Scheduler base hour configs (for interval-triggered jobs)
('scheduler.crawl_base_hour', '0', 'Crawl job base hour (0-23) for interval calculation', 0),
('scheduler.ai_process_base_hour', '0', 'AI process job base hour (0-23) for interval calculation', 0),
('scheduler.embedding_base_hour', '0', 'Embedding job base hour (0-23) for interval calculation', 0),
('scheduler.action_extract_base_hour', '0', 'Action extract job base hour (0-23) for interval calculation', 0),
-- Pipeline batch limits
('pipeline.ai_batch_limit', '200', 'AI processing batch limit per run', 0),
('pipeline.embedding_batch_limit', '500', 'Embedding computation batch limit per run', 0),
('pipeline.event_batch_limit', '500', 'Event clustering batch limit per run', 0),
('pipeline.action_batch_limit', '200', 'Action extraction batch limit per run', 0),
('pipeline.translate_batch_limit', '100', 'Title translation batch limit per run', 0),
('pipeline.worker_interval_minutes', '10', 'Pipeline worker polling interval in minutes', 0),
-- Retention 配置
('retention.active_days', '7', 'Article active retention days', 0),
('retention.archive_days', '30', 'Archive retention days', 0),
('retention.backup_enabled', 'true', 'Enable automatic backup', 0),
-- Cache 配置
('cache.enabled', 'false', 'Enable caching', 0),
('cache.default_ttl', '300', 'Default cache TTL in seconds', 0),
-- JWT 配置
('jwt.access_token_expire_minutes', '1440', 'Access token expiration in minutes (default: 1 day)', 0),
('jwt.refresh_token_expire_days', '7', 'Refresh token expiration in days', 0),
-- 每日报告配置
('daily_report.enabled', 'true', '是否启用每日报告功能', 0),
('daily_report.hour', '8', '每日报告生成时间（小时，0-23）', 0),
('daily_report.minute', '0', '每日报告生成时间（分钟，0-59）', 0),
('daily_report.categories', 'cs.LG,cs.CV,cs.CL,cs.AI,cs.RO,cs.NE', '要生成报告的 arXiv 分类（逗号分隔）', 0),
('daily_report.max_articles', '50', '每个分类最大文章数', 0),
('daily_report.translate_title', 'true', '是否翻译标题', 0),
('daily_report.translate_batch_size', '10', '翻译分批大小（每批处理后更新进度）', 0),
('daily_report.report_offset_days', '1', '报告相对于今天的偏移天数（1=昨天）', 0),
('ai.translate_concurrency', '5', '批量翻译并发数', 0);

-- =============================================================================
-- 默认话题数据
-- =============================================================================
-- 初始化系统默认话题，覆盖 AI 领域的主要研究方向
INSERT INTO topics (name, description, keywords, is_auto_discovered, is_active, created_at, updated_at) VALUES
('GPT-4', 'OpenAI GPT-4 模型相关研究与应用', '["GPT-4", "GPT4", "GPT-4o", "GPT-4-turbo"]', 0, 1, NOW(), NOW()),
('大模型', '大规模语言模型研究与发展', '["大模型", "LLM", "大语言模型", "语言模型"]', 0, 1, NOW(), NOW()),
('Claude', 'Anthropic Claude 模型相关内容', '["Claude", "Claude-3", "Anthropic"]', 0, 1, NOW(), NOW()),
('Gemini', 'Google Gemini 多模态模型', '["Gemini", "Google AI", "Bard"]', 0, 1, NOW(), NOW()),
('计算机视觉', '计算机视觉与图像处理研究', '["计算机视觉", "CV", "图像识别", "目标检测"]', 0, 1, NOW(), NOW()),
('AI Agent', 'AI 智能体与自动化应用', '["Agent", "智能体", "AI Agent", "Autonomous"]', 0, 1, NOW(), NOW()),
('开源模型', '开源大模型与社区项目', '["开源", "Llama", "Mistral", "Qwen"]', 0, 1, NOW(), NOW()),
('机器学习', '机器学习算法与理论研究', '["机器学习", "ML", "深度学习", "神经网络"]', 0, 1, NOW(), NOW()),
('NLP', '自然语言处理技术', '["NLP", "自然语言处理", "文本分析", "语义理解"]', 0, 1, NOW(), NOW()),
('强化学习', '强化学习算法与应用', '["强化学习", "RL", "DQN", "PPO"]', 0, 1, NOW(), NOW()),
('多模态', '多模态学习与跨模态理解', '["多模态", "Multimodal", "视觉语言"]', 0, 1, NOW(), NOW()),
('RAG', '检索增强生成技术', '["RAG", "检索增强", "知识库", "向量检索"]', 0, 1, NOW(), NOW()),
('AI 芯片', 'AI 芯片与硬件加速', '["AI芯片", "GPU", "TPU", "NPU", "算力"]', 0, 1, NOW(), NOW()),
('AI 安全', 'AI 安全与对齐研究', '["AI安全", "对齐", "Alignment", "安全"]', 0, 1, NOW(), NOW()),
('自动驾驶', '自动驾驶技术与智能交通', '["自动驾驶", "无人驾驶", "智能驾驶"]', 0, 1, NOW(), NOW()),
('机器人', '机器人技术与具身智能', '["机器人", "具身智能", "Embodied AI"]', 0, 1, NOW(), NOW()),
('语音识别', '语音识别与语音合成技术', '["语音识别", "ASR", "TTS", "语音合成"]', 0, 1, NOW(), NOW()),
('AI 绘画', 'AI 图像生成与艺术创作', '["AI绘画", "Stable Diffusion", "Midjourney"]', 0, 1, NOW(), NOW()),
('代码生成', 'AI 代码生成与辅助编程', '["代码生成", "Copilot", "CodeLlama"]', 0, 1, NOW(), NOW()),
('创业融资', 'AI 领域创业与投资动态', '["创业", "融资", "投资", "独角兽"]', 0, 1, NOW(), NOW());

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


-- ============================================================
-- OPML Import: user-provided feed collection (2026-03-23)
-- is_active=0 by default; enable selectively
-- ============================================================
INSERT IGNORE INTO `rss_feeds` (`title`, `feed_url`, `site_url`, `category`, `description`, `is_active`, `country`, `news_category`) VALUES
  ('Hack Sparrow', 'http://feeds.feedburner.com/hacksparrow', '', 'blog', '', 0, 'EN', NULL),
  ('NodeUp', 'http://feeds.feedburner.com/NodeUp', '', 'blog', '', 0, 'EN', NULL),
  ('Node.js Blog', 'https://nodejs.org/en/feed/blog.xml', '', 'blog', '', 0, 'EN', NULL),
  ('Vue.js - MVVM Made Simple', 'https://www.reddit.com/r/vuejs/.rss', '', 'blog', '', 0, 'EN', NULL),
  ('Vue.js Feed', 'https://vuejsfeed.com/feed', '', 'blog', '', 0, 'EN', NULL),
  ('技术小黑屋', 'https://droidyue.com/atom.xml', 'http://droidyue.com/', 'blog', '', 0, 'CN', NULL),
  ('张明云的博客', 'http://zmywly8866.github.io/pages/atom.xml', 'http://zmywly8866.github.io', 'blog', '', 0, 'CN', NULL),
  ('开源实验室', 'http://www.kymjs.com/feed.xml', 'http://www.kymjs.com/', 'blog', '', 0, 'CN', NULL),
  ('子勰的博客', 'https://blog.bihe0832.com/pages/atom.xml', 'http://blog.bihe0832.com', 'blog', '', 0, 'CN', NULL),
  ('博客园_漫天尘沙', 'https://feed.cnblogs.com/blog/u/162102/rss', '', 'blog', '', 0, 'CN', NULL),
  ('WaylenWang', 'http://waylenw.github.io/atom.xml', 'http://waylenw.github.io/', 'blog', '', 0, 'EN', NULL),
  ('云风的 BLOG', 'https://blog.codingnow.com/atom.xml', 'http://blog.codingnow.com/', 'blog', '', 0, 'CN', NULL),
  ('Trinea', 'https://www.trinea.cn/feed/', 'http://www.trinea.cn', 'blog', '', 0, 'CN', NULL),
  ('The Corner', 'http://feeds.feedburner.com/corner-squareup-com', 'http://corner.squareup.com', 'blog', '', 0, 'EN', NULL),
  ('Mobile Internet developer', 'https://rss.csdn.net/xiaanming/rss/map', '', 'blog', '', 0, 'CN', NULL),
  ('inovex-Blog', 'https://www.inovex.de/de/feed/', 'https://blog.inovex.de', 'blog', '', 0, 'EN', NULL),
  ('Loader\'s Blog', 'https://rss.csdn.net/qibin0506/rss/map', '', 'blog', '', 0, 'CN', NULL),
  ('ASCE1885', 'https://rss.csdn.net/asce1885/rss/map', '', 'blog', '', 0, 'CN', NULL),
  ('Android Central', 'https://www.androidcentral.com/feeds.xml', '', 'blog', '', 0, 'EN', NULL),
  ('风雪之隅', 'https://www.laruence.com/feed', 'http://www.laruence.com', 'blog', '', 0, 'EN', NULL),
  ('杨辉的个人博客', 'http://yanghui.name/atom.xml', 'http://yanghui.name/', 'blog', '', 0, 'CN', NULL),
  ('快乐de胖虎', 'https://rss.csdn.net/u011133213/rss/map', '', 'blog', '', 0, 'CN', NULL),
  ('张兴业的博客', 'https://rss.csdn.net/xyz_lmn/rss/map', '', 'blog', '', 0, 'CN', NULL),
  ('四火的唠叨', 'https://www.raychase.net/feed', 'http://www.raychase.net', 'blog', '', 0, 'CN', NULL),
  ('Tricky Android', 'http://trickyandroid.com/feed/', '', 'blog', '', 0, 'EN', NULL),
  ('The Cheese Factory\'s Blog', 'https://inthecheesefactory.com/blog/en/rss.xml', '', 'blog', '', 0, 'EN', NULL),
  ('MacTalk-池建强的随想录', 'https://macshuo.com/?feed=rss2', 'http://macshuo.com', 'blog', '', 0, 'CN', NULL),
  ('Android Performance', 'https://androidperformance.com/atom.xml', '', 'blog', '', 0, 'EN', NULL),
  ('Innost的专栏', 'https://rss.csdn.net/innost/rss/map', '', 'blog', '', 0, 'CN', NULL),
  ('Dan Lew Codes', 'https://blog.danlew.net/rss/', '', 'blog', '', 0, 'EN', NULL),
  ('Android Design Patterns', 'https://www.androiddesignpatterns.com/feed.atom', '', 'blog', '', 0, 'EN', NULL),
  ('AigeStudio', 'https://rss.csdn.net/aigestudio/rss/map', '', 'blog', '', 0, 'CN', NULL),
  ('Framer Blog', 'https://framerjs.tumblr.com/rss', '', 'blog', '', 0, 'EN', NULL),
  ('[ i D 公 社 ]', 'http://feeds.feedburner.com/ID', 'http://www.hi-id.com', 'blog', '', 0, 'CN', NULL),
  ('Be For Web', 'http://beforweb.com/rss.xml', '', 'blog', '', 0, 'EN', NULL),
  ('NullPointer的新无效地址', 'http://npchen.blogspot.com/feeds/posts/default', '', 'blog', '', 0, 'EN', NULL),
  ('peter.michaux.ca', 'http://peter.michaux.ca/feed/atom.xml', '', 'blog', '', 0, 'EN', NULL),
  ('Fonts In Use', 'https://fontsinuse.com/blog.rss', '', 'blog', '', 0, 'EN', NULL),
  ('James Burke', 'http://jrburke.com/atom.xml', '', 'blog', '', 0, 'EN', NULL),
  ('MooTools', 'http://feeds.feedburner.com/mootools-blog', '', 'blog', '', 0, 'EN', NULL),
  ('Smashing Magazine', 'https://www.smashingmagazine.com/feed/', '', 'blog', '', 0, 'EN', NULL),
  ('岁月如歌', 'https://lifesinger.wordpress.com/feed/', '', 'blog', '', 0, 'EN', NULL),
  ('韩寒', 'https://blog.sina.com.cn/rss/twocold.xml', '', 'blog', '', 0, 'CN', NULL),
  ('粉丝日志', 'http://blog.fens.me/feed/', '', 'blog', '', 0, 'CN', NULL),
  ('Coding Horror', 'https://blog.codinghorror.com/rss/', '', 'blog', '', 0, 'EN', NULL),
  ('Julia Evans', 'https://jvns.ca/atom.xml', 'http://jvns.ca', 'blog', '', 0, 'EN', NULL),
  ('Brendan Gregg\'s Blog', 'https://www.brendangregg.com/blog/rss.xml', '', 'blog', '', 0, 'EN', NULL),
  ('Inside Intercom', 'https://www.intercom.com/blog/feed/', '', 'blog', '', 0, 'EN', NULL),
  ('Backchannel', 'https://medium.com/feed/backchannel', '', 'blog', '', 0, 'EN', NULL),
  ('Palantir Blog', 'https://medium.com/feed/palantir', '', 'blog', '', 0, 'EN', NULL),
  ('Instagram Engineering', 'https://instagram-engineering.tumblr.com/rss', '', 'blog', '', 0, 'EN', NULL),
  ('Grab Tech', 'https://engineering.grab.com/feed.xml', '', 'blog', '', 0, 'EN', NULL),
  ('LessWrong', 'https://www.lesswrong.com/feed.xml', '', 'blog', '', 0, 'EN', NULL),
  ('六六六六六六', 'https://liuliu.me/atom.xml', '', 'blog', '', 0, 'CN', NULL),
  ('Tim Pope\'s Blog', 'https://tbaggery.com/atom.xml', '', 'blog', '', 0, 'EN', NULL),
  ('Robert Heaton', 'https://robertheaton.com/feed.xml', '', 'blog', '', 0, 'EN', NULL),
  ('The Register', 'https://www.theregister.com/headlines.atom', '', 'blog', '', 0, 'EN', NULL),
  ('Mattermark', 'https://mattermark.com/feed/', '', 'blog', '', 0, 'EN', NULL),
  ('Antirez weblog', 'https://antirez.com/rss', '', 'blog', '', 0, 'EN', NULL),
  ('Mike Ash', 'https://www.mikeash.com/pyblog/rss.py', '', 'blog', '', 0, 'EN', NULL),
  ('NSHipster', 'https://nshipster.com/feed.xml', '', 'blog', '', 0, 'EN', NULL),
  ('Natasha The Robot', 'https://www.natashatherobot.com/feed', '', 'blog', '', 0, 'EN', NULL),
  ('objc.io', 'https://www.objc.io/feed.xml', '', 'blog', '', 0, 'EN', NULL),
  ('Cocoa with Love', 'https://www.cocoawithlove.com/feed.xml', '', 'blog', '', 0, 'EN', NULL),
  ('iOS Dev Weekly', 'https://iosdevweekly.com/issues.rss', '', 'blog', '', 0, 'EN', NULL),
  ('AppCoda', 'https://www.appcoda.com/rss/', '', 'blog', '', 0, 'EN', NULL),
  ('Raywenderlich', 'https://www.kodeco.com/feed/', '', 'blog', '', 0, 'EN', NULL),
  ('SwiftRocks', 'https://swiftrocks.com/rss.xml', '', 'blog', '', 0, 'EN', NULL),
  ('Ole Begemann', 'https://oleb.net/blog/atom.xml', '', 'blog', '', 0, 'EN', NULL),
  ('OneV\'s Den', 'https://onevcat.com/feed.xml', '', 'blog', '', 0, 'EN', NULL),
  ('卖鱼的程序员', 'http://blog.sunnyxx.com/atom.xml', '', 'blog', '', 0, 'CN', NULL),
  ('bang\'s blog', 'http://blog.cnbang.net/feed/', '', 'blog', '', 0, 'EN', NULL),
  ('ibireme的博客', 'https://blog.ibireme.com/feed/', '', 'blog', '', 0, 'CN', NULL),
  ('美团点评技术团队', 'https://tech.meituan.com/feed/', '', 'blog', '', 0, 'CN', NULL),
  ('AlloyTeam', 'http://www.alloyteam.com/feed/', '', 'blog', '', 0, 'EN', NULL),
  ('张鑫旭-鑫空间-鑫生活', 'https://www.zhangxinxu.com/wordpress/feed/', '', 'blog', '', 0, 'CN', NULL),
  ('mobibrw.com', 'https://www.mobibrw.com/feed', '', 'blog', '', 0, 'EN', NULL),
  ('唐巧的技术博客', 'http://blog.devtang.com/atom.xml', '', 'blog', '', 0, 'CN', NULL),
  ('阮一峰的网络日志', 'http://www.ruanyifeng.com/blog/atom.xml', 'http://www.ruanyifeng.com/blog', 'blog', '', 0, 'CN', NULL),
  ('Livid / Bruce', 'http://livid.v2ex.com/feed.xml', '', 'blog', '', 0, 'CN', NULL),
  ('西乔 / 神秘的程序员们', 'http://feeds.feedburner.com/mystuff', '', 'blog', '', 0, 'CN', NULL),
  ('李开复', 'https://blog.sina.com.cn/rss/kaifulee.xml', '', 'blog', '', 0, 'CN', NULL),
  ('淡然', 'https://wudaijun.com/atom.xml', '', 'blog', '', 0, 'CN', NULL),
  ('byvoid', 'https://byvoid.com/zht/feed.xml', '', 'blog', '', 0, 'CN', NULL),
  ('Fenng 冯大辉', 'https://medium.com/feed/@fenng', '', 'blog', '', 0, 'EN', NULL),
  ('虫叔', 'http://maoao530.github.io/atom.xml', '', 'blog', '', 0, 'EN', NULL),
  ('博客园 - 精华', 'https://feed.cnblogs.com/blog/sitehome/rss', '', 'blog', '', 0, 'CN', NULL),
  ('Vamei', 'https://feed.cnblogs.com/blog/u/118754/rss/', '', 'blog', '', 0, 'CN', NULL),
  ('draveness的博客', 'https://draven.co/feed.xml', '', 'blog', '', 0, 'CN', NULL),
  ('卧龙岗上的码农', 'https://feed.cnblogs.com/blog/u/312210/rss/', '', 'blog', '', 0, 'CN', NULL),
  ('技术派', 'http://www.techupdate.cn/feed.xml', '', 'blog', '', 0, 'CN', NULL),
  ('Facebook 工程团队', 'https://engineering.fb.com/feed/', '', 'blog', '', 0, 'CN', NULL),
  ('Amazon Science', 'https://www.amazon.science/index.rss', '', 'blog', '', 0, 'EN', NULL),
  ('Google Research Blog', 'http://feeds.feedburner.com/blogspot/gJZg', '', 'blog', '', 0, 'EN', NULL),
  ('CodePen Blog', 'https://blog.codepen.io/feed/', '', 'reference', '', 0, 'EN', NULL),
  ('Lobsters', 'https://lobste.rs/rss', '', 'tech', '', 0, 'EN', NULL),
  ('Echo JS', 'https://www.echojs.com/rss', '', 'tech', '', 0, 'EN', NULL),
  ('JavaScript Weekly', 'https://cprss.s3.amazonaws.com/javascriptweekly.com.xml', '', 'tech', '', 0, 'EN', NULL),
  ('Node Weekly', 'https://cprss.s3.amazonaws.com/nodeweekly.com.xml', '', 'tech', '', 0, 'EN', NULL),
  ('Ruby Weekly', 'https://cprss.s3.amazonaws.com/rubyweekly.com.xml', '', 'tech', '', 0, 'EN', NULL),
  ('StatusCode Weekly', 'https://cprss.s3.amazonaws.com/weekly.statuscode.com.xml', '', 'tech', '', 0, 'EN', NULL),
  ('Golang Weekly', 'https://cprss.s3.amazonaws.com/golangweekly.com.xml', '', 'tech', '', 0, 'EN', NULL),
  ('Database Weekly', 'https://cprss.s3.amazonaws.com/dbweekly.com.xml', '', 'tech', '', 0, 'EN', NULL),
  ('Postgres Weekly', 'https://cprss.s3.amazonaws.com/postgresweekly.com.xml', '', 'tech', '', 0, 'EN', NULL),
  ('Nicholas C. Zakas', 'https://humanwhocodes.com/feeds/blog.xml', '', 'tech', '', 0, 'EN', NULL),
  ('Paul Irish', 'http://feeds.feedburner.com/paul-irish', '', 'tech', '', 0, 'EN', NULL),
  ('David Walsh Blog', 'https://davidwalsh.name/feed', '', 'tech', '', 0, 'EN', NULL),
  ('Robin Wieruch', 'https://www.robinwieruch.de/index.xml', '', 'tech', '', 0, 'EN', NULL),
  ('Dan Abramov', 'https://overreacted.io/rss.xml', '', 'tech', '', 0, 'EN', NULL),
  ('kentcdodds', 'https://kentcdodds.com/blog/rss.xml', '', 'tech', '', 0, 'EN', NULL),
  ('Cindy Sridharan', 'https://medium.com/feed/@copyconstruct', '', 'tech', '', 0, 'EN', NULL),
  ('Thoughtworks Insights', 'https://www.thoughtworks.com/rss/insights.xml', '', 'tech', '', 0, 'EN', NULL),
  ('Sam Newman', 'https://samnewman.io/blog/feed.xml', '', 'tech', '', 0, 'EN', NULL),
  ('High Scalability', 'http://feeds.feedburner.com/HighScalability', '', 'tech', '', 0, 'EN', NULL),
  ('The Morning Paper', 'https://blog.acolyer.org/feed/', '', 'tech', '', 0, 'EN', NULL),
  ('Joel on Software', 'https://www.joelonsoftware.com/feed/', '', 'blog', '', 0, 'EN', NULL),
  ('Seth Godin\'s Blog', 'http://feeds.feedblitz.com/sethsblog', '', 'blog', '', 0, 'EN', NULL),
  ('Wait But Why', 'https://waitbutwhy.com/feed', '', 'blog', '', 0, 'EN', NULL),
  ('Derek Sivers', 'https://sive.rs/en.atom', '', 'blog', '', 0, 'EN', NULL),
  ('Stratechery', 'https://stratechery.com/feed/', '', 'blog', '', 0, 'EN', NULL),
  ('Naval Ravikant', 'https://nav.al/feed', '', 'blog', '', 0, 'EN', NULL),
  ('SegmentFault 思否', 'https://segmentfault.com/feeds', '', 'community', '', 0, 'CN', NULL),
  ('GitHub Engineering', 'https://github.blog/engineering.atom', '', 'tech', '', 0, 'EN', NULL),
  ('GitHub Changelog', 'https://github.blog/changelog/feed/', '', 'tech', '', 0, 'EN', NULL),
  ('GitHub Actions', 'https://github.blog/feed/?cat=product', '', 'tech', '', 0, 'EN', NULL),
  ('The Changelog', 'https://changelog.com/feed', '', 'tech', '', 0, 'EN', NULL),
  ('Hacker News Front Page', 'https://hnrss.org/frontpage', '', 'tech', '', 0, 'EN', NULL),
  ('TLDR Newsletter', 'https://tldr.tech/api/rss/tech', '', 'tech', '', 0, 'EN', NULL),
  ('SRE Weekly', 'https://sreweekly.com/feed/', '', 'tech', '', 0, 'EN', NULL),
  ('Increment Magazine', 'https://increment.com/feed.xml', '', 'tech', '', 0, 'EN', NULL),
  ('MIT News - Computer Science', 'https://news.mit.edu/rss/topic/computers', '', 'tech', '', 0, 'EN', NULL),
  ('Stanford AI Lab Blog', 'http://ai.stanford.edu/blog/feed.xml', '', 'tech', '', 0, 'EN', NULL),
  ('The Pragmatic Engineer', 'https://blog.pragmaticengineer.com/rss/', '', 'tech', '', 0, 'EN', NULL),
  ('Tech Lead Journal', 'https://techleadjournal.dev/index.xml', '', 'life', '', 0, 'EN', NULL),
  ('The Pragmatic Engineer Newsletter', 'https://newsletter.pragmaticengineer.com/feed', '', 'life', '', 0, 'EN', NULL),
  ('LeadDev', 'https://leaddev.com/feed', '', 'life', '', 0, 'EN', NULL),
  ('Software Engineering Daily', 'https://softwareengineeringdaily.com/feed/', '', 'life', '', 0, 'EN', NULL),
  ('Pat Kua', 'https://www.patkua.com/blog/feed/', '', 'life', '', 0, 'EN', NULL),
  ('Camille Fournier', 'https://www.elidedbranches.com/feeds/posts/default', '', 'life', '', 0, 'EN', NULL),
  ('Charity Majors', 'https://charity.wtf/feed/', '', 'life', '', 0, 'EN', NULL),
  ('Rands in Repose', 'https://randsinrepose.com/feed/', '', 'life', '', 0, 'EN', NULL),
  ('Will Larson', 'https://lethain.com/feeds/', '', 'life', '', 0, 'EN', NULL),
  ('The Engineering Manager', 'https://www.theengineeringmanager.com/feed/', '', 'life', '', 0, 'EN', NULL),
  ('Software at Scale', 'https://www.softwareatscale.dev/feed', '', 'life', '', 0, 'EN', NULL),
  ('Discord Engineering', 'https://discord.com/blog/rss.xml', '', 'life', '', 0, 'EN', NULL),
  ('HashiCorp Blog', 'https://www.hashicorp.com/blog/feed.xml', '', 'life', '', 0, 'EN', NULL),
  ('Kubernetes Blog', 'https://kubernetes.io/feed.xml', '', 'life', '', 0, 'EN', NULL),
  ('AWS Architecture Blog', 'https://aws.amazon.com/blogs/architecture/feed/', '', 'life', '', 0, 'EN', NULL),
  ('开源中国', 'https://www.oschina.net/news/rss', '', 'tech', '', 0, 'CN', NULL),
  ('Google Developers Blog', 'https://developers.googleblog.com/feeds/posts/default/', '', 'tech', '', 0, 'EN', NULL),
  ('VentureBeat', 'https://venturebeat.com/feed', '', 'tech', '', 0, 'EN', NULL),
  ('ReadWrite', 'https://readwrite.com/feed/', '', 'tech', '', 0, 'EN', NULL),
  ('Mashable Tech', 'http://feeds.mashable.com/mashable/tech', '', 'tech', '', 0, 'EN', NULL),
  ('Fast Company', 'https://www.fastcompany.com/latest/rss?format=xml', '', 'tech', '', 0, 'EN', NULL),
  ('科技爱好者周刊', 'https://feeds2.feedburner.com/ruanyifeng', '', 'tech', '', 0, 'CN', NULL),
  ('Hacker News Daily', 'https://www.daemonology.net/hn-daily/index.rss', '', 'tech', '', 0, 'EN', NULL),
  ('Reddit Programming', 'https://www.reddit.com/r/programming/.rss', '', 'tech', '', 0, 'EN', NULL),
  ('Reddit Technology', 'https://www.reddit.com/r/technology/.rss', '', 'tech', '', 0, 'EN', NULL),
  ('Reddit WebDev', 'https://www.reddit.com/r/webdev/.rss', '', 'tech', '', 0, 'EN', NULL),
  ('Dev.to', 'https://dev.to/feed', '', 'tech', '', 0, 'EN', NULL),
  ('Medium – Programming', 'https://medium.com/feed/tag/programming', '', 'tech', '', 0, 'EN', NULL),
  ('Sidebar.io', 'https://sidebar.io/feed.xml', '', 'tech', '', 0, 'EN', NULL),
  ('raywenderlich.com', 'https://www.kodeco.com/feed', '', 'mobile_tech', '', 0, 'EN', NULL),
  ('Cocoa with Love', 'https://cocoawithlove.com/feed.xml', '', 'mobile_tech', '', 0, 'EN', NULL),
  ('inessential', 'https://inessential.com/xml/rss.xml', '', 'mobile_tech', '', 0, 'EN', NULL),
  ('Daring Fireball', 'https://daringfireball.net/feeds/main', '', 'mobile_tech', '', 0, 'EN', NULL),
  ('Marco Arment', 'https://marco.org/rss', '', 'mobile_tech', '', 0, 'EN', NULL),
  ('One Foot Tsunami', 'https://onefoottsunami.com/feed/atom/', '', 'mobile_tech', '', 0, 'EN', NULL),
  ('Six Colors', 'https://sixcolors.com/feed/', '', 'mobile_tech', '', 0, 'EN', NULL),
  ('512 Pixels', 'https://512pixels.net/feed/', '', 'mobile_tech', '', 0, 'EN', NULL),
  ('Swift Forums', 'https://forums.swift.org/latest.rss', '', 'mobile_tech', '', 0, 'EN', NULL),
  ('Hacking with Swift', 'https://www.hackingwithswift.com/articles/rss', '', 'mobile_tech', '', 0, 'EN', NULL),
  ('Use Your Loaf', 'https://useyourloaf.com/blog/rss.xml', '', 'mobile_tech', '', 0, 'EN', NULL),
  ('Donny Wals', 'https://www.donnywals.com/feed/', '', 'mobile_tech', '', 0, 'EN', NULL),
  ('Antoine van der Lee', 'https://www.avanderlee.com/feed/', '', 'mobile_tech', '', 0, 'EN', NULL),
  ('Sketch Blog', 'https://www.sketch.com/blog/feed.xml', '', 'design', '', 0, 'EN', NULL),
  ('Nielsen Norman Group', 'https://www.nngroup.com/feed/rss/', '', 'design', '', 0, 'EN', NULL),
  ('The Old New Thing', 'https://devblogs.microsoft.com/oldnewthing/feed', '', 'programming', '', 0, 'EN', NULL),
  ('Eric Lippert', 'https://ericlippert.com/feed/', '', 'programming', '', 0, 'EN', NULL),
  ('Dan Luu', 'https://danluu.com/atom.xml', '', 'programming', '', 0, 'EN', NULL),
  ('Marc Brooker', 'https://brooker.co.za/blog/rss.xml', '', 'programming', '', 0, 'EN', NULL),
  ('Basecs', 'https://medium.com/feed/basecs', '', 'programming', '', 0, 'EN', NULL),
  ('Hillel Wayne', 'https://www.hillelwayne.com/post/index.xml', '', 'programming', '', 0, 'EN', NULL),
  ('Lambda the Ultimate', 'http://lambda-the-ultimate.org/rss.xml', '', 'programming', '', 0, 'EN', NULL),
  ('Andreas Kling', 'https://awesomekling.github.io/feed.xml', '', 'programming', '', 0, 'EN', NULL),
  ('John Carmack (Inlined)', 'http://the-witness.net/news/feed/', '', 'programming', '', 0, 'EN', NULL),
  ('Eli Bendersky\'s website', 'https://eli.thegreenplace.net/feeds/all.atom.xml', '', 'programming', '', 0, 'EN', NULL),
  ('Amos Wenger (fasterthanlime)', 'https://fasterthanli.me/index.xml', '', 'programming', '', 0, 'EN', NULL),
  ('Armin Ronacher', 'https://lucumr.pocoo.org/feed.atom', '', 'programming', '', 0, 'EN', NULL),
  ('Raymond Hettinger', 'https://rhettinger.wordpress.com/feed/', '', 'programming', '', 0, 'EN', NULL),
  ('Ned Batchelder', 'https://nedbatchelder.com/blog/rss.xml', '', 'programming', '', 0, 'EN', NULL),
  ('tef (without a name)', 'https://programmingisterrible.com/rss', '', 'programming', '', 0, 'EN', NULL),
  ('Coding for SSDs', 'https://codecapsule.com/feed/', '', 'programming', '', 0, 'EN', NULL),
  ('Peter Norvig', 'http://norvig.com/rss-feed.xml', '', 'programming', '', 0, 'EN', NULL),
  ('The Rust Blog', 'https://blog.rust-lang.org/feed.xml', '', 'programming', '', 0, 'EN', NULL),
  ('Go Blog', 'https://go.dev/blog/feed.atom', '', 'programming', '', 0, 'EN', NULL),
  ('Haskell Weekly', 'https://haskellweekly.news/newsletter.atom', '', 'programming', '', 0, 'EN', NULL),
  ('Planet Clojure', 'https://planet.clojure.in/atom.xml', '', 'programming', '', 0, 'EN', NULL),
  ('This Week in Rust', 'https://this-week-in-rust.org/rss.xml', '', 'programming', '', 0, 'EN', NULL),
  ('CSS Weekly', 'https://css-weekly.com/feed', '', 'programming', '', 0, 'EN', NULL),
  ('Frontend Focus', 'https://cprss.s3.amazonaws.com/frontendfoc.us.xml', '', 'programming', '', 0, 'EN', NULL),
  ('Vue.js News', 'https://news.vuejs.org/feed.xml', '', 'programming', '', 0, 'EN', NULL),
  ('React Status', 'https://react.statuscode.com/rss', '', 'programming', '', 0, 'EN', NULL),
  ('Real Python', 'https://realpython.com/atom.xml', '', 'programming', '', 0, 'EN', NULL),
  ('Planet Python', 'https://planetpython.org/rss20.xml', '', 'programming', '', 0, 'EN', NULL),
  ('Papers We Love', 'https://paperswelove.org/feed.xml', '', 'programming', '', 0, 'EN', NULL),
  ('CNCF Blog', 'https://www.cncf.io/blog/feed/', '', 'programming', '', 0, 'EN', NULL),
  ('The Sweet Setup', 'https://thesweetsetup.com/feed/', '', 'tech', '', 0, 'EN', NULL),
  ('Mathbabe', 'https://mathbabe.org/feed/', '', 'math', '', 0, 'EN', NULL),
  ('Math ∩ Programming', 'https://www.jeremykun.com/index.xml', '', 'math', '', 0, 'EN', NULL),
  ('Better Explained', 'https://betterexplained.com/feed/', '', 'math', '', 0, 'EN', NULL),
  ('Terence Tao\'s Blog', 'https://terrytao.wordpress.com/feed/', '', 'math', '', 0, 'EN', NULL),
  ('ccjou', 'https://ccjou.wordpress.com/feed/', '', 'math', '', 0, 'EN', NULL);

-- =============================================================================
-- content_themes 初始数据
-- 预置 5 套主题：经典蓝（默认）、深色雅致、科技蓝、暖色系、清爽薄荷
-- 适用范围: daily_report, weekly_report, email_digest
-- 格式化器: wechat_html, email_html
-- =============================================================================

-- 先删除旧数据（避免重复插入）
DELETE FROM `content_themes` WHERE name IN (
  'classic_blue', 'elegant_dark', 'tech_blue', 'warm_brown', 'mint_fresh'
);

INSERT INTO `content_themes`
  (`name`, `display_name`, `description`, `content_types`, `formatter_types`, `config`,
   `is_default`, `is_active`, `priority`, `preview_url`, `author`, `created_at`, `updated_at`)
VALUES

-- 1. 经典蓝（默认）
(
  'classic_blue', '经典蓝', '清爽简洁的蓝色风格，系统默认主题',
  JSON_ARRAY('daily_report', 'weekly_report', 'email_digest'),
  JSON_ARRAY('wechat_html', 'email_html'),
  JSON_OBJECT(
    'colors', JSON_OBJECT(
      'title_color',         '#1a1a1a',
      'title_color_dark',    '#1a1a2e',
      'subtitle_color',      '#3e3e3e',
      'section_title_color', '#1e6bb8',
      'text_color',          '#3e3e3e',
      'meta_color',          '#888888',
      'link_color',          '#576b95',
      'link_color_cyan',     '#4ecdc4',
      'accent_color',        '#1e6bb8',
      'border_color',        '#e5e5e5',
      'bg_light',            '#f7f7f7',
      'bg_email',            '#f5f5f7',
      'bg_email_light',      '#f0f2f5',
      'success_color',       '#2ecc71',
      'error_color',         '#e74c3c',
      'warning_color',       '#f59e0b',
      'source_arxiv',        '#b31b1b',
      'source_rss',          '#f5a623',
      'source_wechat',       '#07c160'
    )
  ),
  1, 1, 100, NULL, 'ResearchPulse', NOW(), NOW()
),

-- 2. 深色雅致
(
  'elegant_dark', '深色雅致', '高雅深色风格，适合夜间阅读',
  JSON_ARRAY('daily_report', 'weekly_report', 'email_digest'),
  JSON_ARRAY('wechat_html', 'email_html'),
  JSON_OBJECT(
    'colors', JSON_OBJECT(
      'title_color',         '#e8e8e8',
      'title_color_dark',    '#1a1a1a',
      'subtitle_color',      '#c0c0c0',
      'section_title_color', '#7a9ec4',
      'text_color',          '#b0b0b0',
      'meta_color',          '#808080',
      'link_color',          '#7a9ec4',
      'link_color_cyan',     '#5eb3b3',
      'accent_color',        '#7a9ec4',
      'border_color',        '#333333',
      'bg_light',            '#2a2a2a',
      'bg_email',            '#1a1a1a',
      'bg_email_light',      '#222222',
      'success_color',       '#66bb6a',
      'error_color',         '#ef5350',
      'warning_color',       '#ffa726',
      'source_arxiv',        '#ef5350',
      'source_rss',          '#ff9800',
      'source_wechat',       '#66bb6a'
    )
  ),
  0, 1, 90, NULL, 'ResearchPulse', NOW(), NOW()
),

-- 3. 科技蓝
(
  'tech_blue', '科技蓝', '现代科技感风格，视觉冲击力强',
  JSON_ARRAY('daily_report', 'weekly_report', 'email_digest'),
  JSON_ARRAY('wechat_html', 'email_html'),
  JSON_OBJECT(
    'colors', JSON_OBJECT(
      'title_color',         '#1f2937',
      'title_color_dark',    '#0f172a',
      'subtitle_color',      '#4b5563',
      'section_title_color', '#2563eb',
      'text_color',          '#374151',
      'meta_color',          '#6b7280',
      'link_color',          '#2563eb',
      'link_color_cyan',     '#06b6d4',
      'accent_color',        '#2563eb',
      'border_color',        '#e5e7eb',
      'bg_light',            '#f3f4f6',
      'bg_email',            '#f9fafb',
      'bg_email_light',      '#f3f4f6',
      'success_color',       '#10b981',
      'error_color',         '#ef4444',
      'warning_color',       '#f59e0b',
      'source_arxiv',        '#dc2626',
      'source_rss',          '#fb923c',
      'source_wechat',       '#16a34a'
    )
  ),
  0, 1, 80, NULL, 'ResearchPulse', NOW(), NOW()
),

-- 4. 暖色系
(
  'warm_brown', '暖色系', '温暖舒适的棕色风格，亲切自然',
  JSON_ARRAY('daily_report', 'weekly_report', 'email_digest'),
  JSON_ARRAY('wechat_html', 'email_html'),
  JSON_OBJECT(
    'colors', JSON_OBJECT(
      'title_color',         '#5a3a1a',
      'title_color_dark',    '#3e2723',
      'subtitle_color',      '#6d4c41',
      'section_title_color', '#c97c5c',
      'text_color',          '#5a3a1a',
      'meta_color',          '#8d6e63',
      'link_color',          '#d7723e',
      'link_color_cyan',     '#d7723e',
      'accent_color',        '#c97c5c',
      'border_color',        '#d7ccc8',
      'bg_light',            '#efebe9',
      'bg_email',            '#fafaf8',
      'bg_email_light',      '#f5f5f1',
      'success_color',       '#81c784',
      'error_color',         '#e57373',
      'warning_color',       '#ffb74d',
      'source_arxiv',        '#e64a19',
      'source_rss',          '#fb8500',
      'source_wechat',       '#52b788'
    )
  ),
  0, 1, 70, NULL, 'ResearchPulse', NOW(), NOW()
),

-- 5. 清爽薄荷
(
  'mint_fresh', '清爽薄荷', '清新薄荷绿风格，清爽怡人',
  JSON_ARRAY('daily_report', 'weekly_report', 'email_digest'),
  JSON_ARRAY('wechat_html', 'email_html'),
  JSON_OBJECT(
    'colors', JSON_OBJECT(
      'title_color',         '#0d3b3d',
      'title_color_dark',    '#004d4d',
      'subtitle_color',      '#2a6b6e',
      'section_title_color', '#2d9597',
      'text_color',          '#2a5a5d',
      'meta_color',          '#5a8b8e',
      'link_color',          '#2d9597',
      'link_color_cyan',     '#00bcd4',
      'accent_color',        '#1db7b9',
      'border_color',        '#b2dfdb',
      'bg_light',            '#e0f2f1',
      'bg_email',            '#f1f8f7',
      'bg_email_light',      '#e0f2f1',
      'success_color',       '#26a69a',
      'error_color',         '#ef5350',
      'warning_color',       '#ffa726',
      'source_arxiv',        '#d32f2f',
      'source_rss',          '#ff9800',
      'source_wechat',       '#00897b'
    )
  ),
  0, 1, 60, NULL, 'ResearchPulse', NOW(), NOW()
);
