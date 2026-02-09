# 云服务器部署指南

本指南将帮助你将德州扑克游戏部署到云服务器（如阿里云、腾讯云、AWS等）。

## 目录
- [部署方式](#部署方式)
- [方式一：Docker部署（推荐）](#方式一docker部署推荐)
- [方式二：传统部署](#方式二传统部署)
- [配置HTTPS](#配置https)
- [常见问题](#常见问题)

---

## 部署方式

我们提供两种部署方式：
1. **Docker部署**（推荐）：简单、快速、隔离性好
2. **传统部署**：直接在服务器上运行

---

## 方式一：Docker部署（推荐）

### 前置要求

- 云服务器（1核2G内存以上）
- Ubuntu 20.04 或更高版本
- Root权限

### 步骤1：上传文件到服务器

```bash
# 在本地打包文件
tar -czf poker-game.tar.gz poker_game.py ai_player.py main.py index.html \
    requirements.txt Dockerfile docker-compose.yml nginx.conf deploy.sh

# 上传到服务器
scp poker-game.tar.gz root@your-server-ip:/root/
```

### 步骤2：连接服务器并解压

```bash
# SSH连接服务器
ssh root@your-server-ip

# 解压文件
cd /root
tar -xzf poker-game.tar.gz
cd poker-game
```

### 步骤3：运行部署脚本

```bash
# 自动部署（推荐）
chmod +x deploy.sh
./deploy.sh
```

或手动部署：

```bash
# 安装Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# 安装Docker Compose
curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# 构建并启动
docker-compose up -d

# 安装Nginx
apt-get update
apt-get install -y nginx

# 配置Nginx
cp nginx.conf /etc/nginx/sites-available/poker-game
ln -s /etc/nginx/sites-available/poker-game /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
```

### 步骤4：配置防火墙

```bash
# 开放端口
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 22/tcp

# 如需启用防火墙
ufw enable
```

### 步骤5：访问游戏

打开浏览器访问：`http://your-server-ip`

### Docker常用命令

```bash
# 查看日志
docker-compose logs -f

# 重启应用
docker-compose restart

# 停止应用
docker-compose down

# 更新应用
git pull  # 如果使用git
docker-compose up -d --build

# 查看运行状态
docker-compose ps
```

---

## 方式二：传统部署

### 步骤1：安装Python和依赖

```bash
# 更新系统
apt-get update
apt-get upgrade -y

# 安装Python和pip
apt-get install -y python3 python3-pip python3-venv nginx

# 创建应用目录
mkdir -p /opt/poker-game
cd /opt/poker-game

# 上传文件（使用scp或git）
# ...

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 步骤2：创建systemd服务

创建文件 `/etc/systemd/system/poker-game.service`:

```ini
[Unit]
Description=Texas Poker Game
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/poker-game
Environment="PATH=/opt/poker-game/venv/bin"
ExecStart=/opt/poker-game/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
systemctl daemon-reload
systemctl enable poker-game
systemctl start poker-game
systemctl status poker-game
```

### 步骤3：配置Nginx

使用提供的 `nginx.conf` 文件：

```bash
cp nginx.conf /etc/nginx/sites-available/poker-game
ln -s /etc/nginx/sites-available/poker-game /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
```

---

## 配置HTTPS

### 使用Let's Encrypt（免费）

```bash
# 安装Certbot
apt-get install -y certbot python3-certbot-nginx

# 获取证书（替换your-domain.com为你的域名）
certbot --nginx -d your-domain.com

# 自动续期
certbot renew --dry-run
```

### 手动配置SSL

如果你有自己的SSL证书：

1. 上传证书文件到 `/etc/ssl/certs/`
2. 编辑 `nginx.conf`，取消HTTPS部分的注释
3. 修改证书路径
4. 重启Nginx：`systemctl restart nginx`

---

## 常见问题

### Q1: 无法访问游戏

**检查项**:
```bash
# 检查应用是否运行
docker-compose ps  # Docker方式
systemctl status poker-game  # 传统方式

# 检查端口
netstat -tulpn | grep 8000

# 检查Nginx
systemctl status nginx
nginx -t

# 查看日志
docker-compose logs -f  # Docker
journalctl -u poker-game -f  # 传统方式
tail -f /var/log/nginx/error.log
```

### Q2: WebSocket连接失败

**解决方案**:
- 确保Nginx配置中包含WebSocket支持
- 检查防火墙是否开放80和443端口
- 查看浏览器控制台错误信息

### Q3: 如何更新游戏

**Docker方式**:
```bash
cd /opt/poker-game
# 更新文件...
docker-compose up -d --build
```

**传统方式**:
```bash
cd /opt/poker-game
source venv/bin/activate
# 更新文件...
systemctl restart poker-game
```

### Q4: 如何备份游戏数据

目前游戏数据存储在内存中，重启会丢失。如需持久化：

```bash
# 备份整个应用目录
tar -czf poker-game-backup-$(date +%Y%m%d).tar.gz /opt/poker-game

# 定期备份（crontab）
0 2 * * * tar -czf /backup/poker-game-$(date +\%Y\%m\%d).tar.gz /opt/poker-game
```

### Q5: 如何监控服务器

```bash
# 安装监控工具
apt-get install -y htop

# 查看资源使用
htop

# 查看Docker容器资源
docker stats

# 查看磁盘使用
df -h

# 查看内存使用
free -h
```

### Q6: 游戏卡顿或延迟高

**优化建议**:
1. 升级服务器配置（至少2核4G）
2. 使用CDN加速静态资源
3. 开启Nginx gzip压缩
4. 优化数据库查询（如果添加了数据库）
5. 检查网络带宽

---

## 推荐云服务器配置

### 入门配置
- CPU: 1核
- 内存: 2GB
- 带宽: 3Mbps
- 系统: Ubuntu 20.04
- **适合**: 测试和小规模使用（<10人在线）

### 标准配置（推荐）
- CPU: 2核
- 内存: 4GB
- 带宽: 5Mbps
- 系统: Ubuntu 20.04
- **适合**: 正式运营（<50人在线）

### 高级配置
- CPU: 4核
- 内存: 8GB
- 带宽: 10Mbps
- 系统: Ubuntu 20.04
- **适合**: 大规模使用（>50人在线）

---

## 云服务器提供商

### 国内
- **阿里云**: https://www.aliyun.com/
- **腾讯云**: https://cloud.tencent.com/
- **华为云**: https://www.huaweicloud.com/

### 国外
- **AWS**: https://aws.amazon.com/
- **DigitalOcean**: https://www.digitalocean.com/
- **Vultr**: https://www.vultr.com/

---

## 安全建议

1. **修改SSH端口**
```bash
vim /etc/ssh/sshd_config
# Port 22 改为其他端口
systemctl restart sshd
```

2. **禁用密码登录，使用SSH密钥**
```bash
ssh-keygen -t rsa -b 4096
ssh-copy-id root@your-server-ip
```

3. **配置防火墙**
```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

4. **定期更新系统**
```bash
apt-get update
apt-get upgrade -y
```

5. **安装fail2ban防止暴力破解**
```bash
apt-get install -y fail2ban
systemctl enable fail2ban
systemctl start fail2ban
```

---

## 性能优化

### Nginx优化

编辑 `/etc/nginx/nginx.conf`:

```nginx
worker_processes auto;
worker_connections 2048;

gzip on;
gzip_vary on;
gzip_proxied any;
gzip_comp_level 6;
gzip_types text/plain text/css text/xml text/javascript 
           application/json application/javascript application/xml+rss;
```

### 系统优化

```bash
# 增加文件描述符限制
echo "* soft nofile 65535" >> /etc/security/limits.conf
echo "* hard nofile 65535" >> /etc/security/limits.conf

# 优化TCP参数
cat >> /etc/sysctl.conf << EOF
net.ipv4.tcp_fin_timeout = 30
net.ipv4.tcp_tw_reuse = 1
net.core.somaxconn = 1024
EOF

sysctl -p
```

---

## 技术支持

如遇到问题，请检查：
1. 服务器日志
2. Nginx错误日志
3. 应用日志
4. 浏览器控制台

需要帮助？请提供：
- 错误信息
- 服务器配置
- 操作步骤

---

**祝部署顺利！** 🎉
