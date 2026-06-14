import asyncio
import uvicorn
from .config import settings
from .web import app
from .downloader import download_worker


@app.on_event("startup")
async def app_startup() -> None:
    asyncio.create_task(download_worker())


def run():
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
