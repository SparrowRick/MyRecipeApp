# 情侣空间 (Lover's Space)

情侣专属私密 Web 应用，支持共享菜谱、日记、纪念册、愿望清单、每日问答等功能。

## 功能一览

| 模块 | 说明 |
|------|------|
| 共享菜谱 | 添加/浏览菜谱，支持按种类和按添加人分组；可导入 [HowToCook](https://github.com/Anduin2017/HowToCook) 外部菜谱 |
| AI 智能菜单 | 根据人数和口味偏好，AI 结合本地菜谱生成推荐菜单 |
| 共享日记 | 日历视图，双方各自写日记，互相可见 |
| 每日问答 | AI 每日生成互动问题，双方回答后解锁对方答案；支持点赞偏好学习 |
| 纪念册 | 图文回忆记录，支持上传图片 |
| 愿望清单 | 双方共同维护，可标记完成 |
| 冰箱贴 | 纪念日/倒数日，显示在首页 |
| 伴侣绑定 | 邀请码机制，绑定后共享所有数据 |
| Web 推送通知 | 写日记/回答问题后自动推送通知伴侣 |
| PWA 支持 | 可安装到手机桌面，支持离线缓存 |

## 技术栈

- **后端**: Flask (Python)
- **数据库**: SQLite (Flask-SQLAlchemy + Flask-Migrate)
- **认证**: Flask-Login (session-based)
- **AI**: DashScope API (deepseek-v4-flash)
- **前端**: Jinja2 + TailwindCSS (CDN) + Lucide Icons
- **推送**: pywebpush (Web Push API + VAPID)
- **PWA**: Service Worker + manifest.json

## 快速开始

### 1. 安装依赖

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. 初始化数据库

```bash
set FLASK_APP=app.py   # Windows
export FLASK_APP=app.py # macOS/Linux

flask db upgrade
```

### 3. 导入外部菜谱（可选）

```bash
python import_howtocook.py
```

### 4. 启动应用

```bash
flask run
```

访问 `http://localhost:5000`，注册账号即可使用。

## 配置说明

在 `app.py` 中修改以下配置项：

| 配置项 | 说明 |
|--------|------|
| `SECRET_KEY` | 会话加密密钥，生产环境务必修改 |
| `DASHSCOPE_API_KEY` | 阿里云 DashScope API Key（AI 功能必需） |
| `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` | Web Push VAPID 密钥对（通过环境变量设置） |

生成 VAPID 密钥：

```bash
npx web-push generate-vapid-keys
```

将生成的公钥和私钥分别设置为环境变量 `VAPID_PUBLIC_KEY` 和 `VAPID_PRIVATE_KEY`。

## 部署

```bash
# 拉取最新代码后
flask db upgrade
# 重启 Web 服务器
```

建议使用 Gunicorn + Nginx 部署，Supervisor 管理进程。

## 项目结构

```
MyRecipeApp/
├── app.py                  # 主应用（路由、模型、配置）
├── import_howtocook.py     # HowToCook 菜谱导入脚本
├── requirements.txt        # Python 依赖
├── recipes.db              # SQLite 数据库
├── static/
│   ├── manifest.json       # PWA 清单
│   ├── sw.js               # Service Worker
│   ├── icon.png            # 应用图标
│   └── uploads/            # 用户上传的图片
├── templates/              # Jinja2 模板
│   ├── base.html
│   ├── index.html
│   ├── recipes_list.html
│   ├── recipe_detail.html
│   ├── add_recipe.html
│   ├── ai_menu.html
│   ├── journal.html
│   ├── daily_question.html
│   ├── memories.html
│   ├── wishlist.html
│   └── partner.html
└── migrations/             # 数据库迁移文件
```
