"""DCPAM Web 后端：组装 FastAPI app 与运行入口。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import state
from .routes import camera, config, measurements, preview

app = FastAPI(title="DCPAM Server")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    state._close_camera()


app.router.lifespan_context = _lifespan

app.include_router(camera.router)
app.include_router(preview.router)
app.include_router(measurements.router)
app.include_router(config.router)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(host: str = "127.0.0.1", port: int = 8011, reload: bool = False) -> None:
    import uvicorn

    if reload:
        # reload 需要 import 字符串（reloader 会重新导入 app），且必须在主线程运行
        uvicorn.run(
            "dcpam_app.server.app:app",
            host=host,
            port=port,
            log_level="warning",
            reload=True,
            reload_dirs=["dcpam_app", "dcpam"],
        )
    else:
        uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    import os

    run(
        host=os.environ.get("DCPAM_HOST", "127.0.0.1"),
        port=int(os.environ.get("DCPAM_PORT", "8011")),
        reload=os.environ.get("DCPAM_NO_RELOAD") != "1",
    )
