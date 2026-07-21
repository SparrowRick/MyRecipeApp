# 我们的小窝

仅供两个人使用的 Flask 情侣空间，包含共享日记、每日问答、回忆、愿望、菜谱、重要日子、每日状态、本周小结与 Web Push 通知。

## 本次版本重点

- 日记采用原子保存、本地草稿和通知队列，修复 iOS Safari 偶发丢失问题。
- 每日问题不再每天强制刷新：双方完成回答或明确跳过后才关闭。
- AI 只参考最近 10 道问题的紧凑反馈，并在本地过滤重复、空泛和复杂问题。
- 手机端使用底部导航，支持 iPhone 安全区和软键盘。
- 关闭公开注册；私密页面不再进入 Service Worker 缓存。

## 安装

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

将 `.env` 中的占位值替换为真实配置，并由部署工具加载环境变量。项目不会自动读取 `.env`，生产环境可使用 Supervisor、systemd、Docker 或托管平台配置环境变量。

关键配置：

- `APP_ENV=production`
- `SECRET_KEY`：新的随机长字符串；轮换后现有登录会话失效。
- `DASHSCOPE_API_KEY`：新的 DashScope Key。
- `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY`：新的推送密钥；轮换后需要在设置页重新开启通知。
- `ALLOW_REGISTRATION=false`：默认关闭公开注册。
- `RELATIONSHIP_START_DATE=YYYY-MM-DD`
- `SESSION_COOKIE_SECURE=true`：公网 HTTPS 部署必须开启。
- `DATABASE_URL`：默认使用项目目录下的 `recipes.db`。

> 旧代码曾包含真实密钥。部署前必须在对应平台撤销旧 DashScope 和 VAPID 密钥，而不只是从 Git 历史中删除字符串。

## 升级与启动

升级前先备份：

```powershell
.\.venv\Scripts\python.exe backup_data.py
```

然后执行：

```powershell
$env:FLASK_APP = "app.py"
.\.venv\Scripts\python.exe -m flask db upgrade
.\.venv\Scripts\python.exe -m flask run
```

迁移会保留历史问题和回答，但会关闭旧版问题；升级后首次进入问答页时按新规则生成问题。

## 推送通知队列

保存日记和回答不会等待推送服务返回。应用会立即尝试后台发送，失败记录保留在 `notification_outbox`。部署环境可定时执行：

```powershell
$env:FLASK_APP = "app.py"
.\.venv\Scripts\python.exe -m flask process-notifications
```

## 备份

`backup_data.py` 使用 SQLite 在线备份 API 创建一致的数据库副本，并压缩 `static/uploads`。默认保留最近 14 组备份：

```powershell
.\.venv\Scripts\python.exe backup_data.py --keep 14
```

## 测试

测试不会调用 AI 接口，也不会批量生成问题：

```powershell
$env:APP_ENV = "development"
$env:DATABASE_URL = "sqlite:///:memory:"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

真实 iPhone 上重点检查：断网、切后台、锁屏恢复、重复保存、PWA 模式和重新开启推送。
