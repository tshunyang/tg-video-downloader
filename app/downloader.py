import asyncio
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

from .models import DownloadTask, DownloadStatus
from .config import settings

_tasks: Dict[str, DownloadTask] = {}
_lock = asyncio.Lock()
_active_downloads: set[str] = set()
_download_handles: dict[str, object] = {}
_history_file = settings.project_root / 'task_history.json'
_history: Dict[str, DownloadTask] = {}
_max_concurrent_downloads = max(1, int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2")))


def _status_value(status) -> str:
    if isinstance(status, DownloadStatus):
        return status.value
    text = str(status)
    if text.startswith('DownloadStatus.'):
        return text.split('.', 1)[1].lower()
    return text


def _save_history() -> None:
    _history_file.write_text(json.dumps([t.model_dump(mode='json') for t in _history.values()], ensure_ascii=False, indent=2), encoding='utf-8')


def load_history() -> None:
    global _history, _tasks
    if not _history_file.exists():
        _history = {}
        _tasks = {}
        return
    try:
        data = json.loads(_history_file.read_text(encoding='utf-8'))
        _history = {i['id']: DownloadTask.model_validate(i) for i in data}
        _tasks = {}
        for task in _history.values():
            if _status_value(task.status) in {'pending', 'downloading'}:
                task.status = DownloadStatus.PENDING
                task.error = None
                _tasks[task.id] = task
    except Exception:
        _history = {}
        _tasks = {}


def _sync_task(task: DownloadTask) -> None:
    _history[task.id] = task.model_copy(deep=True)
    _save_history()


def _safe_filename(name: str, fallback: str = "download.bin") -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", name).strip().strip(".")
    return cleaned or fallback


def _render_filename(task: DownloadTask) -> str:
    original = _safe_filename(Path(task.file_name).name or f"{task.id}.bin", f"{task.id}.bin")
    original_path = Path(original)
    stem = _safe_filename(original_path.stem, task.id)
    ext = original_path.suffix
    created = task.created_at or datetime.now()
    date_format = settings.app_config.naming.date_format or "%Y-%m-%d"
    try:
        date_text = created.strftime(date_format)
    except Exception:
        date_text = created.strftime("%Y-%m-%d")
    tokens = {
        "original": original,
        "stem": stem,
        "ext": ext,
        "date": date_text,
        "datetime": created.strftime("%Y-%m-%d_%H-%M-%S"),
        "chat_id": str(task.chat_id),
        "message_id": str(task.message_id),
        "type": getattr(task.media_type, "value", str(task.media_type)),
    }
    pattern = settings.app_config.naming.pattern or "{original}"
    try:
        rendered = pattern.format_map(tokens)
    except Exception:
        rendered = original
    rendered = _safe_filename(rendered, original)
    if not Path(rendered).suffix and ext:
        rendered = f"{rendered}{ext}"
    return rendered


def _part_path_for(path: Path) -> Path:
    return path.with_name(path.name + ".part")


def _next_available_path(target: Path) -> Path:
    if not target.exists() and not _part_path_for(target).exists():
        return target
    stem, suffix, idx = target.stem, target.suffix, 1
    while True:
        candidate = target.with_name(f"{stem}_{idx}{suffix}")
        if not candidate.exists() and not _part_path_for(candidate).exists():
            return candidate
        idx += 1


def _prepare_paths(task: DownloadTask, download_dir: Path) -> tuple[Path, Path]:
    if task.target_path:
        target = Path(task.target_path)
    else:
        target = download_dir / _render_filename(task)
        strategy = settings.app_config.naming.conflict_strategy
        if strategy == "rename":
            target = _next_available_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target, Path(task.temp_path) if task.temp_path else _part_path_for(target)


def _delete_partial_files(task: DownloadTask) -> list[str]:
    deleted = []
    status = _status_value(task.status)
    candidates = []
    if task.temp_path:
        candidates.append(Path(task.temp_path))
    if task.target_path:
        target = Path(task.target_path)
        candidates.append(_part_path_for(target))
        if status != "completed":
            candidates.append(target)

    seen = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            if path.exists() and path.is_file():
                path.unlink()
                deleted.append(str(path))
        except FileNotFoundError:
            pass
    return deleted


def _configured_download_dirs() -> list[Path]:
    sp = settings.app_config.storage_paths
    candidates = [
        settings.download_dir,
        Path(sp.base_dir or settings.download_dir),
        Path(sp.video_dir or ""),
        Path(sp.image_dir or ""),
        Path(sp.document_dir or ""),
        Path(sp.other_dir or ""),
    ]
    dirs = []
    for candidate in candidates:
        try:
            path = candidate.expanduser().resolve()
        except Exception:
            continue
        if path.exists() and path.is_dir() and path not in dirs:
            dirs.append(path)
    return dirs


def cleanup_orphan_partial_files() -> dict:
    protected = set()
    for task in list_tasks().values():
        if _status_value(task.status) in {"pending", "downloading", "paused", "error"} and task.temp_path:
            protected.add(str(Path(task.temp_path).resolve()))

    deleted = []
    deleted_bytes = 0
    failed = {}
    for folder in _configured_download_dirs():
        for part_file in folder.rglob("*.part"):
            try:
                resolved = str(part_file.resolve())
                if resolved in protected:
                    continue
                size = part_file.stat().st_size
                part_file.unlink()
                deleted.append(resolved)
                deleted_bytes += size
            except Exception as e:
                failed[str(part_file)] = str(e)
    return {"deleted": deleted, "deleted_count": len(deleted), "deleted_bytes": deleted_bytes, "failed": failed}


def list_tasks() -> Dict[str, DownloadTask]:
    out = dict(_history)
    out.update(_tasks)
    return out


def get_task(task_id: str):
    return _tasks.get(task_id) or _history.get(task_id)


async def add_task(task: DownloadTask) -> bool:
    async with _lock:
        if task.id in _tasks:
            return False
        ex = _history.get(task.id)
        if ex and _status_value(ex.status) not in {'error', 'canceled', 'paused'}:
            return False
        _tasks[task.id] = task
        _sync_task(task)
        return True


async def set_task_status(task_id: str, status: DownloadStatus, error: str | None = None):
    async with _lock:
        task = _tasks.get(task_id) or _history.get(task_id)
        if not task:
            return
        task.status = status
        if error is not None:
            task.error = error
        if status != DownloadStatus.ERROR and task.error and error is None:
            task.error = None
        _sync_task(task)


async def update_task_progress(task_id: str, downloaded: int, total: int | None = None):
    async with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task.downloaded = downloaded
        if total and total > 0:
            task.file_size = total
        if task.file_size > 0:
            task.progress_percent = round(task.downloaded * 100 / task.file_size, 2)
        _sync_task(task)


async def pause_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise RuntimeError('任务不存在或不在运行中')
    if task.status != DownloadStatus.DOWNLOADING:
        raise RuntimeError('只有下载中的任务才能暂停')
    handle = _download_handles.get(task_id)
    if handle and callable(getattr(handle, 'cancel', None)):
        handle.cancel()
    await set_task_status(task_id, DownloadStatus.PAUSED, '已暂停')


async def cancel_task(task_id: str):
    task = _tasks.get(task_id) or _history.get(task_id)
    if not task:
        raise RuntimeError('任务不存在')
    if _status_value(task.status) == 'completed':
        raise RuntimeError('已完成任务不能取消')
    handle = _download_handles.get(task_id)
    if handle and callable(getattr(handle, 'cancel', None)):
        handle.cancel()
    deleted = _delete_partial_files(task)
    async with _lock:
        current = _tasks.get(task_id) or _history.get(task_id)
        if current:
            current.status = DownloadStatus.CANCELED
            current.error = None
            current.downloaded = 0
            current.progress_percent = 0
            current.saved_path = None
            current.temp_path = None
            if deleted:
                current.target_path = None
            _sync_task(current)
    _active_downloads.discard(task_id)


async def retry_task(task_id: str):
    async with _lock:
        task = _tasks.get(task_id) or _history.get(task_id)
        if not task:
            raise RuntimeError('任务不存在')
        if _status_value(task.status) not in {'error', 'canceled', 'paused'}:
            raise RuntimeError('当前状态不可重试')
        task.status = DownloadStatus.PENDING
        task.error = None
        if not settings.app_config.naming.resume_enabled:
            task.downloaded = 0
            task.progress_percent = 0
            task.saved_path = None
            task.target_path = None
            task.temp_path = None
        _tasks[task_id] = task
        _sync_task(task)


async def batch_action(task_ids: list[str], action: str) -> dict:
    results = {'ok': [], 'failed': {}}
    for task_id in task_ids:
        try:
            if action == 'pause':
                await pause_task(task_id)
            elif action == 'cancel':
                await cancel_task(task_id)
            elif action in {'retry', 'resume'}:
                await retry_task(task_id)
            else:
                raise RuntimeError('不支持的批量操作')
            results['ok'].append(task_id)
        except Exception as e:
            results['failed'][task_id] = str(e)
    return results


async def _download_one(task: DownloadTask):
    from .telegram_client import ensure_connected
    client = await ensure_connected()
    download_dir = settings.media_dir(task.media_type)
    download_dir.mkdir(parents=True, exist_ok=True)

    async def progress_callback(current: int, total: int):
        await update_task_progress(task.id, current, total)

    try:
        await set_task_status(task.id, DownloadStatus.DOWNLOADING, error=None)
        message = await client.get_messages(task.chat_id, ids=task.message_id)
        if not message or not message.media:
            raise RuntimeError('消息不存在或不包含媒体')
        target_path, temp_path = _prepare_paths(task, download_dir)
        async with _lock:
            current = _tasks.get(task.id)
            if current:
                current.target_path = str(target_path)
                current.temp_path = str(temp_path)
                _sync_task(current)

        strategy = settings.app_config.naming.conflict_strategy
        if target_path.exists() and strategy == "skip":
            async with _lock:
                current = _tasks.get(task.id)
                if current:
                    current.saved_path = str(target_path)
                    current.downloaded = current.file_size or target_path.stat().st_size
                    current.progress_percent = 100
                    current.status = DownloadStatus.COMPLETED
                    current.error = None
                    _sync_task(current)
            return
        if target_path.exists() and strategy == "overwrite":
            target_path.unlink()
        if temp_path.exists() and not settings.app_config.naming.resume_enabled:
            temp_path.unlink()

        resume_from = temp_path.stat().st_size if temp_path.exists() else 0
        total_size = task.file_size or int(getattr(getattr(message, 'file', None), 'size', 0) or 0)
        if total_size and resume_from > total_size:
            temp_path.unlink()
            resume_from = 0
        if resume_from:
            await update_task_progress(task.id, resume_from, total_size)

        download_coro = asyncio.current_task()
        _download_handles[task.id] = download_coro
        mode = "ab" if resume_from else "wb"
        with temp_path.open(mode + "") as out:
            async for chunk in client.iter_download(message.media, offset=resume_from, file_size=total_size or None):
                out.write(chunk)
                resume_from += len(chunk)
                await progress_callback(resume_from, total_size or resume_from)

        if target_path.exists() and strategy == "overwrite":
            target_path.unlink()
        temp_path.replace(target_path)
        saved = str(target_path)
        async with _lock:
            current = _tasks.get(task.id)
            if current and current.status != DownloadStatus.CANCELED:
                current.saved_path = str(saved)
                current.target_path = str(target_path)
                current.temp_path = None
                current.downloaded = target_path.stat().st_size
                current.progress_percent = 100 if current.file_size else current.progress_percent
                current.status = DownloadStatus.COMPLETED
                current.error = None
                _sync_task(current)
    except asyncio.CancelledError:
        current = _tasks.get(task.id) or _history.get(task.id)
        if not (current and current.status == DownloadStatus.CANCELED):
            await set_task_status(task.id, DownloadStatus.PAUSED, '已暂停')
    except Exception as e:
        current = _tasks.get(task.id) or _history.get(task.id)
        if not (current and current.status == DownloadStatus.CANCELED):
            await set_task_status(task.id, DownloadStatus.ERROR, str(e))
    finally:
        _active_downloads.discard(task.id)
        _download_handles.pop(task.id, None)
        if task.id in _tasks and _status_value(_tasks[task.id].status) in {'completed', 'error', 'canceled', 'paused'}:
            _tasks.pop(task.id, None)


async def download_worker():
    from .telegram_client import ensure_connected
    load_history()
    await ensure_connected()
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            pending = []
            async with _lock:
                slots = max(0, _max_concurrent_downloads - len(_active_downloads))
                for task in list(_tasks.values()):
                    if len(pending) >= slots:
                        break
                    if task.status == DownloadStatus.PENDING and task.id not in _active_downloads:
                        pending.append(task)
                        _active_downloads.add(task.id)
            for task in pending:
                asyncio.create_task(_download_one(task))
        except Exception:
            pass
        await asyncio.sleep(1)


def get_dashboard_stats(period: str = "day") -> dict:
    tasks = list_tasks()
    today = datetime.now().date()
    if period == "year":
        period_tasks = [t for t in tasks.values() if t.created_at.date().year == today.year]
        label = "本年"
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        period_tasks = [t for t in tasks.values() if start <= t.created_at.date() <= today]
        label = "本周"
    else:
        period = "day"
        period_tasks = [t for t in tasks.values() if t.created_at.date() == today]
        label = "今日"
    completed = sum(1 for t in period_tasks if _status_value(t.status) == 'completed')
    downloading = sum(1 for t in period_tasks if _status_value(t.status) == 'downloading')
    other = max(0, len(period_tasks) - completed - downloading)
    total = max(1, len(period_tasks))
    c1 = round(completed / total * 100, 1)
    c2 = round(downloading / total * 100, 1)
    chart = f'conic-gradient(#35d39a 0 {c1}%, #6ea8fe {c1}% {c1 + c2}%, #ffb84d {c1 + c2}% 100%)'
    trend = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_tasks = [t for t in tasks.values() if t.created_at.date() == day]
        trend.append({'date': day.strftime('%m-%d'), 'count': len(day_tasks), 'completed': sum(1 for t in day_tasks if _status_value(t.status) == 'completed')})
    return {'period': period, 'period_label': label, 'period_total': len(period_tasks), 'today_total': len(period_tasks), 'today_completed': completed, 'today_downloading': downloading, 'today_other': other, 'today_chart': chart, 'trend': trend, 'status_counts': dict(Counter(_status_value(t.status) for t in tasks.values()))}
