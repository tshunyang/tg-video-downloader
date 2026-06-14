import json
import os
import shutil
from pathlib import Path

from .models import AppConfig, FilterConfig, StorageGuardConfig, StoragePathsConfig, DownloadNamingConfig, ThemeMode, MediaType


class Settings:
    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parent.parent
        self.config_file = self.project_root / "app_config.json"

        api_id = os.getenv("TG_API_ID")
        api_hash = os.getenv("TG_API_HASH")
        download_dir = os.getenv("DOWNLOAD_DIR")
        web_port = os.getenv("WEB_PORT")

        env_path = self.project_root / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key == "TG_API_ID" and not api_id:
                    api_id = value
                elif key == "TG_API_HASH" and not api_hash:
                    api_hash = value
                elif key == "DOWNLOAD_DIR" and not download_dir:
                    download_dir = value
                elif key == "WEB_PORT" and not web_port:
                    web_port = value

        if not api_id or not api_hash:
            raise RuntimeError("缺少 TG_API_ID 或 TG_API_HASH，请在项目根目录的 .env 中配置")

        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.session_name = "tg_video_session"
        self.host = "0.0.0.0"
        self.default_port = int(web_port) if web_port else 8080

        default_dir = download_dir or str(self.project_root / "downloads")
        self.runtime_download_dir = Path(default_dir)
        self.app_config = AppConfig(
            download_dir=str(self.runtime_download_dir),
            web_port=self.default_port,
            theme_mode=ThemeMode.SYSTEM,
            filters=FilterConfig(enabled_types=[MediaType.VIDEO]),
            storage_guard=StorageGuardConfig(),
            storage_paths=StoragePathsConfig(base_dir=str(self.runtime_download_dir)),
            naming=DownloadNamingConfig(),
        )
        self.load_app_config()

    @property
    def download_dir(self) -> Path:
        configured = self.app_config.download_dir or str(self.runtime_download_dir)
        return Path(configured)

    @property
    def port(self) -> int:
        return int(self.app_config.web_port or self.default_port)

    def media_dir(self, media_type: MediaType) -> Path:
        sp = self.app_config.storage_paths
        base = Path(sp.base_dir or self.app_config.download_dir or str(self.runtime_download_dir))
        if sp.unify:
            return base
        mapping = {
            MediaType.VIDEO: sp.video_dir,
            MediaType.IMAGE: sp.image_dir,
            MediaType.DOCUMENT: sp.document_dir,
            MediaType.OTHER: sp.other_dir,
        }
        target = mapping.get(media_type)
        return Path(target) if target else base

    def load_app_config(self) -> AppConfig:
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                self.app_config = AppConfig.model_validate(data)
            except Exception:
                self.app_config = AppConfig(download_dir=str(self.runtime_download_dir), web_port=self.default_port)
        else:
            self.app_config = AppConfig(download_dir=str(self.runtime_download_dir), web_port=self.default_port)
            self.save_app_config()

        if not self.app_config.download_dir:
            self.app_config.download_dir = str(self.runtime_download_dir)
        if not self.app_config.web_port:
            self.app_config.web_port = self.default_port
        if not self.app_config.storage_paths.base_dir:
            self.app_config.storage_paths.base_dir = self.app_config.download_dir
        if not self.app_config.download_dir:
            self.app_config.download_dir = self.app_config.storage_paths.base_dir or str(self.runtime_download_dir)
        return self.app_config

    def save_app_config(self) -> None:
        self.config_file.write_text(self.app_config.model_dump_json(indent=2), encoding="utf-8")

    def update_app_config(self, **kwargs) -> AppConfig:
        for key, value in kwargs.items():
            if value is None:
                continue
            if key == "listened_chats":
                self.app_config.listened_chats = value
            elif key == "download_dir":
                self.app_config.download_dir = value
            elif key == "web_port":
                self.app_config.web_port = int(value)
            elif key == "theme_mode":
                self.app_config.theme_mode = ThemeMode(value)
            elif key == "enabled_types":
                self.app_config.filters.enabled_types = [MediaType(v) for v in value]
            elif key in {"min_size_mb", "max_size_mb"}:
                setattr(self.app_config.filters, key, value)
            elif key in {"min_free_percent", "min_free_gb"}:
                setattr(self.app_config.storage_guard, key, value)
            elif key in {"unify", "base_dir", "video_dir", "image_dir", "document_dir", "other_dir"}:
                setattr(self.app_config.storage_paths, key, value)
            elif key == "naming_pattern":
                self.app_config.naming.pattern = value or "{original}"
            elif key == "date_format":
                self.app_config.naming.date_format = value or "%Y-%m-%d"
            elif key == "conflict_strategy":
                self.app_config.naming.conflict_strategy = value if value in {"rename", "overwrite", "skip"} else "rename"
            elif key == "resume_enabled":
                self.app_config.naming.resume_enabled = bool(value)
        self.save_app_config()
        return self.app_config

    def get_storage_status(self) -> dict:
        target = self.download_dir
        target.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(target)
        total, used, free = usage.total, usage.used, usage.free
        free_percent = (free / total * 100) if total else 0
        free_gb = free / 1024 / 1024 / 1024
        guard = self.app_config.storage_guard
        blocked = False
        reasons = []
        if guard.min_free_percent > 0 and free_percent < guard.min_free_percent:
            blocked = True
            reasons.append(f"剩余空间百分比低于阈值 {guard.min_free_percent}%")
        if guard.min_free_gb > 0 and free_gb < guard.min_free_gb:
            blocked = True
            reasons.append(f"剩余空间低于阈值 {guard.min_free_gb} GB")
        return {"path": str(target), "total_bytes": total, "used_bytes": used, "free_bytes": free, "free_percent": round(free_percent,2), "free_gb": round(free_gb,2), "blocked": blocked, "reasons": reasons, "guard": guard.model_dump()}


settings = Settings()
