import asyncio

from .telegram_client import ensure_connected


async def main() -> None:
    client = await ensure_connected()
    print("=========== 可用会话列表（群组 / 频道 / 私聊） ===========")
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        title = getattr(entity, "title", None) or getattr(entity, "first_name", "") or "(无标题)"
        chat_id = getattr(entity, "id", None)
        kind = entity.__class__.__name__
        print(f"ID: {chat_id:>15} | 类型: {kind:<12} | 标题: {title}")


if __name__ == "__main__":
    asyncio.run(main())
