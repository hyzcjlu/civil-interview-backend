# 公务员面试练习平台 - 后端

FastAPI + SQLAlchemy + MySQL/SQLite 后端服务

## 快速启动

### 1. 安装 Python 依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的数据库密码和通义千问 API Key
```

### 3. 初始化数据库

**方式一：自动初始化**（启动时自动建表+种子数据）
```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8050
```

**方式二：一键部署脚本**（推荐，支持更多选项）
```bash
# 检查数据库状态
python database_setup.py --check

# 初始化数据库（创建表 + 种子数据）
python database_setup.py

# 重置数据库（清空重建）
python database_setup.py --reset
```

### 4. 启动服务

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8050
```

服务启动后访问 http://127.0.0.1:8050/health 验证。

## 默认账号

| 用户名 | 密码 |
|--------|------|
| admin  | admin123 |

## 技术栈

- **框架**: FastAPI 2.0
- **ORM**: SQLAlchemy
- **数据库**: MySQL 8.x（也支持 SQLite）
- **认证**: JWT (OAuth2 + python-jose + bcrypt)
- **AI 评分**: 通义千问 qwen-plus（两阶段评分）
- **语音转文字**: 通义千问 ASR

## 项目结构

```
backend/
├── app/
│   ├── api/v1/routes/    # 路由层
│   ├── core/             # 配置、安全、AI工具
│   ├── db/               # 数据库会话
│   ├── models/           # ORM 模型
│   ├── schemas/          # Pydantic 请求/响应模型
│   └── services/         # 业务逻辑层
├── main.py               # 入口文件
├── database_setup.py     # 一键部署脚本
├── seed.py               # 种子数据
├── two_stage_scoring.py  # 两阶段评分核心
└── requirements.txt
```
