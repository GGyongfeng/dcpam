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

def run(host: str = "127.0.0.1", port: int = 8011) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    run()
