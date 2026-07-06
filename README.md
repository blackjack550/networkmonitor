# 网络出口可达性监控

从 Linux 机器向外定时 ICMP ping + TCP 握手延迟检测，覆盖三大运营商 x 五大地区，Web 仪表盘实时查看。

## 检测维度

| 维度 | 协议 | 指标 | 目标数 |
|------|------|------|--------|
| 海外/国内基准 | ICMP Ping | 可达性、延迟、丢包 | 6 |
| 三大运营商 x 五地区 | TCP 握手 | TCP 连接延迟、可达性 | 15 |

### ICMP 目标

| 名称 | 地址 | 说明 |
|------|------|------|
| Google DNS | 8.8.8.8 | 海外可达性基准 |
| Cloudflare DNS | 1.1.1.1 | 海外可达性基准 |
| 阿里 DNS | 223.5.5.5 | 国内可达性基准 |
| 腾讯 DNS | 119.29.29.29 | 国内可达性基准 |
| 百度 IP | 39.156.66.10 | 国内大型站点 |
| OpenDNS | 208.67.222.222 | 海外可达性辅助 |

### TCP 目标矩阵 (地区 x 运营商)

| 地区 | 电信 | 联通 | 移动 |
|------|------|------|------|
| 华北 | www.bj.189.cn:443 | www.10010.com:443 | www.bj.10086.cn:443 |
| 华东 | www.sh.189.cn:443 | sh.10010.com:443 | www.sh.10086.cn:443 |
| 华南 | www.gd.189.cn:443 | gd.10010.com:443 | www.gd.10086.cn:443 |
| 华中 | www.hb.189.cn:443 | hb.10010.com:443 | www.hb.10086.cn:443 |
| 华西 | www.sc.189.cn:443 | sc.10010.com:443 | www.sc.10086.cn:443 |

## 目录结构

```
network-monitor/
├── keys/                    # SSH 密钥（仅本地，不上传服务器）
│   ├── id_ed25519           #   免密私钥
│   └── id_ed25519.pub       #   公钥（已添加到目标机器 ~/.ssh/authorized_keys）
│
├── config.json              # 监控配置
├── monitor.py               # 采集模块（ping + SQLite 存储）
├── web.py                   # Web 面板（Flask REST API）
├── requirements.txt         # Python 依赖
├── run.sh                   # 启停脚本
├── README.md                # 本文件
│
└── static/                  # Web 前端
    └── index.html           #   仪表盘页面
```

## 服务器部署目录

```
/opt/network-monitor/        # 部署根目录
├── .venv/                   # Python 虚拟环境（自动创建）
├── config.json              # 监控配置
├── monitor.py               # 采集模块
├── web.py                   # Web 面板
├── requirements.txt         # 依赖清单
├── run.sh                   # 启停脚本
│
├── logs/                    # 运行日志（按天分割）
│   └── monitor-YYYYMMDD.log
│
├── data/                    # 监控数据
│   └── monitor.db           #   SQLite 数据库
│
├── monitor.pid              # 进程 PID 文件
│
└── static/                  # Web 前端
    └── index.html
```

## 配置说明 (config.json)

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `targets` | 检测目标列表，每个目标含 `name` 和 `host` | 6 个公网 DNS |
| `ping_count` | 每轮 ping 发包数 | 10 |
| `ping_timeout` | 单次 ping 超时（秒） | 5 |
| `interval_seconds` | 检测间隔（秒） | 60 |
| `data_dir` | 数据存储目录 | `./data` |
| `web.host` | Web 监听地址 | `0.0.0.0` |
| `web.port` | Web 监听端口 | `8080` |

## 检测目标

| 名称 | 地址 | 说明 |
|------|------|------|
| Google DNS | 8.8.8.8 | 海外出口可达性基准 |
| Cloudflare DNS | 1.1.1.1 | 海外出口可达性基准 |
| 阿里 DNS | 223.5.5.5 | 国内可达性基准 |
| 腾讯 DNS | 119.29.29.29 | 国内可达性基准 |
| 百度 | 110.242.68.66 | 国内大型站点 |
| OpenDNS | 208.67.222.222 | 海外可达性辅助 |

## 部署步骤

### 1. 初始化（仅首次）

```bash
# 添加公钥到目标服务器 ~/.ssh/authorized_keys
cat keys/id_ed25519.pub
```

### 2. 上传代码

```bash
# 打包（排除密钥目录）
tar -czf deploy.tar.gz --exclude=keys --exclude=deploy.tar.gz *
# 上传
scp -i keys/id_ed25519 deploy.tar.gz root@10.5.254.204:/tmp/
```

### 3. 解压部署

```bash
ssh -i keys/id_ed25519 root@10.5.254.204 \
  "mkdir -p /opt/network-monitor && cd /opt/network-monitor && tar -xzf /tmp/deploy.tar.gz"
```

### 4. 启动服务

```bash
ssh -i keys/id_ed25519 root@10.5.254.204 \
  "cd /opt/network-monitor && chmod +x run.sh && ./run.sh start"
```

## 运维命令

```bash
# 进入部署目录
cd /opt/network-monitor

# 启动
./run.sh start

# 停止
./run.sh stop

# 重启
./run.sh restart

# 查看状态
./run.sh status

# 查看日志
./run.sh log
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | Web 仪表盘页面 |
| `/api/status` | GET | 所有目标的历史数据（含延迟/丢包时序） |
| `/api/ping_now` | GET | 立即执行一轮 ping 检测 |
| `/api/ping_now?count=5&timeout=3` | GET | 立即检测（自定义参数） |
| `/api/targets` | GET | 获取当前检测目标列表 |
| `/api/reachable_summary` | GET | 各目标可用率汇总 |
| `/api/config` | GET/POST | 查看/修改配置 |

## 更新部署

```bash
# 本地打包
tar -czf deploy.tar.gz --exclude=keys --exclude=deploy.tar.gz *

# 上传
scp -i keys/id_ed25519 deploy.tar.gz root@10.5.254.204:/tmp/

# 远端更新（保留 .venv 和数据）
ssh -i keys/id_ed25519 root@10.5.254.204 "\
  cd /opt/network-monitor && \
  ./run.sh stop; \
  tar -xzf /tmp/deploy.tar.gz --exclude='.venv' --exclude='data' --exclude='logs' --exclude='monitor.pid'; \
  ./run.sh start"
```

## 依赖

- **Linux 服务器**: Python 3.8+, `python3-venv`
- **本地 Windows**: OpenSSH Client, `tar`
