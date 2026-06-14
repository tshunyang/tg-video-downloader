# Open source release checklist

Before publishing this project, make sure these private runtime files are not committed:

- `.env`
- `*.session` and `*.session-journal`
- `app_config.json`
- `task_history.json`
- `downloads/`
- `server.log`
- `app/*.bak-*`

Recommended first release flow:

```bash
git init
git add .
git status
git commit -m "Initial open source release"
```

Build an OpenWrt IPK package:

```bash
python3 packaging/openwrt/build-ipk.py --arch all
```

Install on OpenWrt:

```bash
opkg install dist/tg-video-downloader_0.1.0_all.ipk
vi /etc/tg-video-downloader.env
/etc/init.d/tg-video-downloader start
```
