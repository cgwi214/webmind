-- WebMind 数据库初始化脚本
-- 表结构由后端 SQLAlchemy 自动建表（init_db），这里只负责建库与字符集

CREATE DATABASE IF NOT EXISTS webmind
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

-- 如需独立账号，取消注释并调整密码
-- CREATE USER IF NOT EXISTS 'webmind'@'%' IDENTIFIED BY 'password';
-- GRANT ALL PRIVILEGES ON webmind.* TO 'webmind'@'%';
-- FLUSH PRIVILEGES;
