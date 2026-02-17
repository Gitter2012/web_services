-- =============================================================================
-- 数据迁移脚本: 修复 user_subscriptions 表的 source_type 值
-- 功能: 将旧的 source_type 值更新为正确的订阅类型
-- 执行时机: 在部署新版本代码之前或之后执行均可
-- =============================================================================

-- 开始事务
START TRANSACTION;

-- 1. 更新 ArXiv 类目订阅: arxiv -> arxiv_category
UPDATE `user_subscriptions`
SET `source_type` = 'arxiv_category'
WHERE `source_type` = 'arxiv';

-- 2. 更新 RSS 源订阅: rss -> rss_feed
UPDATE `user_subscriptions`
SET `source_type` = 'rss_feed'
WHERE `source_type` = 'rss';

-- 3. 更新微信公众号订阅: wechat -> wechat_account
UPDATE `user_subscriptions`
SET `source_type` = 'wechat_account'
WHERE `source_type` = 'wechat';

-- 4. 修改表注释 (可选，如果之前已修改过 init.sql 则不需要)
-- ALTER TABLE `user_subscriptions`
--   MODIFY `source_type` VARCHAR(30) NOT NULL COMMENT '来源类型: arxiv_category, rss_feed, wechat_account, weibo_hot_search, hackernews_source, reddit_source, twitter_source';

-- 提交事务
COMMIT;

-- =============================================================================
-- 验证脚本: 检查迁移结果
-- =============================================================================
-- 查看各类型的订阅数量
SELECT
    source_type,
    COUNT(*) as count
FROM `user_subscriptions`
WHERE `is_active` = 1
GROUP BY `source_type`
ORDER BY count DESC;

-- 查看是否还有旧的 source_type 值 (应该返回空结果)
SELECT DISTINCT `source_type`
FROM `user_subscriptions`
WHERE `source_type` IN ('arxiv', 'rss', 'wechat');

-- =============================================================================
-- 回滚脚本 (如果需要)
-- =============================================================================
-- START TRANSACTION;
-- UPDATE `user_subscriptions` SET `source_type` = 'arxiv' WHERE `source_type` = 'arxiv_category';
-- UPDATE `user_subscriptions` SET `source_type` = 'rss' WHERE `source_type` = 'rss_feed';
-- UPDATE `user_subscriptions` SET `source_type` = 'wechat' WHERE `source_type` = 'wechat_account';
-- COMMIT;
