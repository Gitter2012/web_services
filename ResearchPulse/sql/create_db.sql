-- 1. 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS research_pulse
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- 2. 创建用户（请将 'your_password' 替换为强密码）
CREATE USER 'research_user'@'%' IDENTIFIED BY 'your_secure_password';

-- 3. 授予该用户对 research_pulse 数据库的全部权限
GRANT ALL PRIVILEGES ON research_pulse.* TO 'research_user'@'%';

-- 4. 刷新权限
FLUSH PRIVILEGES;
