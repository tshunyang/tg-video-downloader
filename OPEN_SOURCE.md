# 开源发布检查清单

发布 Telegram 媒体资源下载器前，请确认以下私密运行文件没有被提交：

- `.env`
- `*.session` and `*.session-journal`
- `app_config.json`
- `task_history.json`
- `downloads/`
- `server.log`
- `app/*.bak-*`

推荐首次发布流程：

```bash
git init
git add .
git status
git commit -m "Initial open source release"
```

构建 OpenWrt IPK 安装包：

```bash
python3 packaging/openwrt/build-ipk.py --arch all
```

在 OpenWrt 上安装：

```bash
opkg install dist/tg-video-downloader_0.1.0_all.ipk
vi /etc/tg-video-downloader.env
/etc/init.d/tg-video-downloader start
```
