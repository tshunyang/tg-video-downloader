from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELED = "canceled"
    ERROR = "error"


class ThemeMode(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class MediaType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    DOCUMENT = "document"
    OTHER = "other"


class FilterConfig(BaseModel):
    enabled_types: list[MediaType] = Field(default_factory=lambda: [MediaType.VIDEO])
    min_size_mb: float = 0
    max_size_mb: float = 0


class StorageGuardConfig(BaseModel):
    min_free_percent: float = 0
    min_free_gb: float = 0


class StoragePathsConfig(BaseModel):
    unify: bool = True
    base_dir: Optional[str] = None
    video_dir: Optional[str] = None
    image_dir: Optional[str] = None
    document_dir: Optional[str] = None
    other_dir: Optional[str] = None


class DownloadNamingConfig(BaseModel):
    pattern: str = "{original}"
    date_format: str = "%Y-%m-%d"
    conflict_strategy: str = "rename"
    resume_enabled: bool = True


class AppConfig(BaseModel):
    listened_chats: list[int] = Field(default_factory=list)
    download_dir: Optional[str] = None
    web_port: int = 8080
    theme_mode: ThemeMode = ThemeMode.SYSTEM
    filters: FilterConfig = Field(default_factory=FilterConfig)
    storage_guard: StorageGuardConfig = Field(default_factory=StorageGuardConfig)
    storage_paths: StoragePathsConfig = Field(default_factory=StoragePathsConfig)
    naming: DownloadNamingConfig = Field(default_factory=DownloadNamingConfig)


class DownloadTask(BaseModel):
    id: str
    chat_id: int
    message_id: int
    file_name: str
    file_size: int
    media_type: MediaType = MediaType.OTHER
    downloaded: int = 0
    status: DownloadStatus = DownloadStatus.PENDING
    error: Optional[str] = None
    saved_path: Optional[str] = None
    target_path: Optional[str] = None
    temp_path: Optional[str] = None
    progress_percent: float = 0
    created_at: datetime = Field(default_factory=datetime.now)
