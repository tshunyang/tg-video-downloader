# TG Resource Downloader

一个基于 Python、FastAPI 和 Telethon 的 Telegram 资源自动下载器，提供网页管理界面，可监听指定群组 / 频道，并按文件类型、体积、目录和命名规则自动下载资源。

## 功能

- Telegram 个人账号登录
- Web 界面读取并勾选群组 / 频道
- 监听新消息并自动创建下载任务
- 支持视频、图片、文档和其他文件类型过滤
- 支持文件体积范围过滤
- 支持统一目录或按类型分类目录
- 支持命名模板、日期格式和文件冲突处理策略
- 支持断点续传、暂停、继续、取消并删除部分文件
- 支持清理孤儿 `.part` 临时文件
- 支持任务进度、统计概览和日 / 周 / 年视图

## 本地运行

1. 安装依赖：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

2. 创建 `.env`：

```bash
cp .env.example .env
```

填写 Telegram API 信息：

```env
TG_API_ID=你的_api_id
TG_API_HASH=你的_api_hash
WEB_PORT=8080
DOWNLOAD_DIR=./downloads
```

Telegram API ID 和 Hash 可在 <https://my.telegram.org/apps> 创建应用后获取。

3. 启动：

```bash
python -m app.main
```

默认访问：

- 本机：`http://127.0.0.1:8080`
- 局域网：`http://你的IP:8080`

## OpenWrt / IPK

项目内置 OpenWrt IPK 打包脚本：

```bash
python3 packaging/openwrt/build-ipk.py --arch all
```

生成文件位于：

```text
dist/tg-video-downloader_0.1.0_all.ipk
```

安装后编辑配置：

```bash
opkg install dist/tg-video-downloader_0.1.0_all.ipk
vi /etc/tg-video-downloader.env
/etc/init.d/tg-video-downloader start
```

服务文件会将程序安装到 `/opt/tg-video-downloader`，并通过 `/etc/init.d/tg-video-downloader` 由 procd 管理。

## 不要提交的文件

这些文件包含账号、运行状态或下载内容，开源前必须排除：

- `.env`
- `*.session`
- `*.session-journal`
- `app_config.json`
- `task_history.json`
- `downloads/`
- `server.log`
- `app/*.bak-*`

`.gitignore` 已默认排除这些文件。

## License

MIT
