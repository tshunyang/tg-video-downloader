from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

from .config import settings
from .models import DownloadTask, MediaType
from .downloader import add_task

_client: TelegramClient | None = None
_pending_phone: str | None = None
_listening: bool = False
_listened_chats: set[int] = set(settings.app_config.listened_chats)
_handler_registered: bool = False


def get_client() -> TelegramClient:
    global _client
    if _client is None:
        _client = TelegramClient(settings.session_name, settings.api_id, settings.api_hash)
    return _client


async def ensure_connected() -> TelegramClient:
    client = get_client()
    if not client.is_connected():
        await client.connect()
    return client


async def is_authorized() -> bool:
    client = await ensure_connected()
    return await client.is_user_authorized()


async def logout() -> None:
    global _client, _listening, _pending_phone
    client = await ensure_connected()
    await client.log_out()
    await client.disconnect()
    _client = None
    _listening = False
    _pending_phone = None


async def start_login(phone: str) -> None:
    global _pending_phone
    client = await ensure_connected()
    await client.send_code_request(phone)
    _pending_phone = phone


async def complete_login(code: str) -> None:
    global _pending_phone
    if not _pending_phone:
        raise RuntimeError("没有待登录的手机号，请先发起登录")
    client = await ensure_connected()
    try:
        await client.sign_in(_pending_phone, code)
    except SessionPasswordNeededError:
        raise RuntimeError("该账号开启了两步验证，目前暂不支持在网页中输入密码")
    finally:
        _pending_phone = None


async def list_dialogs() -> list[dict]:
    client = await ensure_connected()
    selected = set(_listened_chats)
    items = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        title = getattr(entity, "title", None) or getattr(entity, "first_name", "") or "(无标题)"
        items.append({"id": int(dialog.id), "title": title, "kind": entity.__class__.__name__, "username": getattr(entity, 'username', None), "selected": int(dialog.id) in selected})
    return items


def get_listened_chats() -> list[int]:
    return sorted(_listened_chats)


def set_listened_chats(chat_ids: list[int]) -> None:
    _listened_chats.clear(); _listened_chats.update(chat_ids)
    settings.update_app_config(listened_chats=sorted(_listened_chats))


def is_listening() -> bool:
    return _listening


def _detect_media_type(message) -> MediaType:
    if getattr(message, 'video', None):
        return MediaType.VIDEO
    if getattr(message, 'photo', None):
        return MediaType.IMAGE
    if getattr(message, 'document', None):
        mime = getattr(getattr(message, 'file', None), 'mime_type', '') or ''
        if mime.startswith('image/'):
            return MediaType.IMAGE
        if mime.startswith('video/'):
            return MediaType.VIDEO
        if mime or getattr(getattr(message, 'file', None), 'name', None):
            return MediaType.DOCUMENT
    return MediaType.OTHER


def _message_matches_filters(message, media_type: MediaType) -> tuple[bool, str | None]:
    file = getattr(message, 'file', None)
    suffix = Path(getattr(file, 'name', None) or '').suffix.lower()
    size = int(getattr(file, 'size', 0) or 0)
    filters = settings.app_config.filters

    if media_type not in filters.enabled_types:
        return False, f'文件类型 {media_type.value} 未启用'
    min_bytes = int(filters.min_size_mb * 1024 * 1024)
    max_bytes = int(filters.max_size_mb * 1024 * 1024)
    if min_bytes > 0 and size < min_bytes:
        return False, '文件小于最小体积限制'
    if max_bytes > 0 and size > max_bytes:
        return False, '文件大于最大体积限制'
    storage = settings.get_storage_status()
    if storage['blocked']:
        return False, '存储空间保护已触发：' + '；'.join(storage['reasons'])
    return True, None


async def _handle_media_message(event) -> None:
    if not _listening:
        return
    if _listened_chats and int(event.chat_id) not in _listened_chats:
        return
    message = event.message
    if not (message.video or message.document or message.photo):
        return
    media_type = _detect_media_type(message)
    matched, reason = _message_matches_filters(message, media_type)
    if not matched:
        print(f'[LISTENER] 已跳过消息 {event.chat_id}_{event.id}: {reason}')
        return
    file_name = getattr(getattr(message, 'file', None), 'name', None)
    if not file_name:
        ext = {MediaType.VIDEO: '.mp4', MediaType.IMAGE: '.jpg', MediaType.DOCUMENT: '.bin', MediaType.OTHER: '.bin'}[media_type]
        file_name = f'chat_{event.chat_id}_msg_{event.id}{ext}'
    file_size = int(getattr(getattr(message, 'file', None), 'size', 0) or 0)
    task = DownloadTask(id=f'{event.chat_id}_{event.id}', chat_id=int(event.chat_id), message_id=int(event.id), file_name=file_name, file_size=file_size, media_type=media_type)
    created = await add_task(task)
    if created:
        print(f'[LISTENER] 已创建下载任务: {task.id} -> {task.file_name}')


async def start_listening() -> None:
    global _listening, _handler_registered
    client = await ensure_connected()
    if not _handler_registered:
        client.add_event_handler(_handle_media_message, events.NewMessage())
        _handler_registered = True
    _listening = True


async def stop_listening() -> None:
    global _listening
    _listening = False
