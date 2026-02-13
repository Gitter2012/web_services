-- ResearchPulse v2 Database Initialization Script
-- MySQL 8.0+
-- Run this script to create all tables

-- Set charset and collation
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- ============================================================================
-- User and Permission Tables (RBAC)
-- ============================================================================

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login_at DATETIME NULL,
    -- Email notification settings
    email_notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Whether user wants to receive email notifications',
    email_digest_frequency VARCHAR(20) NOT NULL DEFAULT 'daily' COMMENT 'Email digest frequency: daily, weekly, or none',
    INDEX idx_users_username (username),
    INDEX idx_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Roles table
CREATE TABLE IF NOT EXISTS roles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(255) DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_roles_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Permissions table
CREATE TABLE IF NOT EXISTS permissions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    resource VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    description VARCHAR(255) DEFAULT '',
    INDEX idx_permissions_name (name),
    INDEX idx_permissions_resource (resource)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- User-Role association table
CREATE TABLE IF NOT EXISTS user_roles (
    user_id INT NOT NULL,
    role_id INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Role-Permission association table
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INT NOT NULL,
    permission_id INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- Content Tables
-- ============================================================================

-- Unified articles table
CREATE TABLE IF NOT EXISTS articles (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source_type VARCHAR(20) NOT NULL COMMENT 'Source type: arxiv, rss, wechat',
    source_id VARCHAR(100) NOT NULL COMMENT 'ID of the source',
    external_id VARCHAR(255) DEFAULT '' COMMENT 'External ID from source',
    title VARCHAR(767) NOT NULL DEFAULT '',
    url VARCHAR(2000) NOT NULL DEFAULT '',
    author TEXT NULL,
    summary TEXT,
    content TEXT,
    cover_image_url VARCHAR(2000) DEFAULT '',
    category VARCHAR(200) DEFAULT '',
    tags JSON COMMENT 'JSON array of tags',
    publish_time DATETIME NULL,
    crawl_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    archived_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    -- arxiv specific fields
    arxiv_id VARCHAR(50) NULL COMMENT 'arXiv paper ID',
    arxiv_primary_category VARCHAR(200) NULL,
    arxiv_comment TEXT NULL,
    arxiv_updated_time DATETIME NULL COMMENT 'arXiv updated time',
    -- wechat specific fields
    wechat_account_name VARCHAR(200) NULL,
    wechat_digest TEXT NULL,
    -- summary field for AI-generated summary or translation
    content_summary TEXT NULL COMMENT 'AI summary or translated abstract',
    read_count INT DEFAULT 0,
    like_count INT DEFAULT 0,
    UNIQUE KEY uk_articles_source_external (source_type, source_id, external_id),
    INDEX idx_articles_source_type (source_type),
    INDEX idx_articles_source_id (source_id),
    INDEX idx_articles_category (category),
    INDEX idx_articles_publish_time (publish_time),
    INDEX idx_articles_crawl_time (crawl_time),
    INDEX idx_articles_archived (is_archived)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- arXiv categories table
CREATE TABLE IF NOT EXISTS arxiv_categories (
    id INT PRIMARY KEY AUTO_INCREMENT,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    parent_code VARCHAR(50) DEFAULT '',
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_arxiv_categories_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- RSS feeds table
CREATE TABLE IF NOT EXISTS rss_feeds (
    id INT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(500) NOT NULL DEFAULT '',
    feed_url VARCHAR(767) NOT NULL UNIQUE,
    site_url VARCHAR(767) DEFAULT '',
    category VARCHAR(100) DEFAULT '',
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_fetched_at DATETIME NULL,
    error_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_rss_feeds_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- WeChat accounts table
CREATE TABLE IF NOT EXISTS wechat_accounts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    account_name VARCHAR(100) NOT NULL UNIQUE COMMENT 'WeChat account name (biz)',
    display_name VARCHAR(200) DEFAULT '',
    description TEXT,
    avatar_url VARCHAR(767) DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_fetched_at DATETIME NULL,
    error_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_wechat_accounts_name (account_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- User Subscription and State Tables
-- ============================================================================

-- User subscriptions table
CREATE TABLE IF NOT EXISTS user_subscriptions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    source_type VARCHAR(30) NOT NULL COMMENT 'arxiv_category, rss_feed, wechat_account',
    source_id INT NOT NULL COMMENT 'ID of the subscribed source',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uk_user_subscription (user_id, source_type, source_id),
    INDEX idx_user_subscriptions_type (source_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- User article states table (read/star status)
CREATE TABLE IF NOT EXISTS user_article_states (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    article_id BIGINT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    is_starred BOOLEAN NOT NULL DEFAULT FALSE,
    read_at DATETIME NULL,
    starred_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    UNIQUE KEY uk_user_article (user_id, article_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- System Tables
-- ============================================================================

-- System configuration table
CREATE TABLE IF NOT EXISTS system_config (
    config_key VARCHAR(100) PRIMARY KEY,
    config_value TEXT NOT NULL,
    description VARCHAR(255) DEFAULT '',
    is_sensitive BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by INT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Backup records table
CREATE TABLE IF NOT EXISTS backup_records (
    id INT PRIMARY KEY AUTO_INCREMENT,
    backup_date DATETIME NOT NULL UNIQUE,
    backup_file VARCHAR(500) NOT NULL,
    backup_size BIGINT NOT NULL DEFAULT 0,
    article_count INT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending, completed, failed',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME NULL,
    error_message TEXT NULL,
    INDEX idx_backup_records_date (backup_date),
    INDEX idx_backup_records_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Audit logs table
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(100) DEFAULT '',
    details JSON,
    ip_address VARCHAR(45) DEFAULT '',
    user_agent VARCHAR(500) DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_audit_logs_user (user_id),
    INDEX idx_audit_logs_action (action),
    INDEX idx_audit_logs_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- Seed Data
-- ============================================================================

-- Insert default permissions
INSERT INTO permissions (name, resource, action, description) VALUES
-- Article permissions
('article:read', 'article', 'read', 'View articles'),
('article:list', 'article', 'list', 'List articles'),
-- Subscription permissions
('subscription:create', 'subscription', 'create', 'Create subscriptions'),
('subscription:read', 'subscription', 'read', 'View own subscriptions'),
('subscription:delete', 'subscription', 'delete', 'Delete subscriptions'),
-- User management permissions
('user:manage', 'user', 'manage', 'Manage users'),
('user:list', 'user', 'list', 'List users'),
-- Role management permissions
('role:manage', 'role', 'manage', 'Manage roles'),
('role:list', 'role', 'list', 'List roles'),
-- Crawler management permissions
('crawler:manage', 'crawler', 'manage', 'Manage crawlers'),
('crawler:trigger', 'crawler', 'trigger', 'Trigger crawl tasks'),
-- Config management permissions
('config:manage', 'config', 'manage', 'Manage system config'),
('config:read', 'config', 'read', 'Read system config'),
-- Backup permissions
('backup:manage', 'backup', 'manage', 'Manage backups'),
('backup:restore', 'backup', 'restore', 'Restore from backup')
ON DUPLICATE KEY UPDATE name = VALUES(name);

-- Insert default roles
INSERT INTO roles (name, description) VALUES
('superuser', 'Superuser with all permissions'),
('admin', 'Administrator with management permissions'),
('user', 'Regular user with basic permissions'),
('guest', 'Guest user with read-only access')
ON DUPLICATE KEY UPDATE name = VALUES(name);

-- Assign all permissions to superuser role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p WHERE r.name = 'superuser'
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- Assign specific permissions to admin role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'admin' AND p.name IN (
    'article:read', 'article:list',
    'user:manage', 'user:list',
    'role:list',
    'crawler:manage', 'crawler:trigger',
    'config:read', 'config:manage',
    'backup:manage'
)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- Assign specific permissions to user role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'user' AND p.name IN (
    'article:read', 'article:list',
    'subscription:create', 'subscription:read', 'subscription:delete'
)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- Assign specific permissions to guest role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'guest' AND p.name IN ('article:read', 'article:list')
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- ============================================================================
-- Finish
-- ============================================================================

SELECT 'Database initialization completed successfully!' AS message;
