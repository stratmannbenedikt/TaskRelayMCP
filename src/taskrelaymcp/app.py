from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from taskrelaymcp.api import router
from taskrelaymcp.config import authenticate
from taskrelaymcp.db import init_db
from taskrelaymcp.mcp_server import mcp

mcp_app = mcp.http_app(path="/", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    async with mcp_app.lifespan(app):
        yield


app = FastAPI(title="TaskRelay", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def protect_mcp(request: Request, call_next):
    if request.url.path.startswith("/mcp") and not authenticate(request.headers.get("authorization")):
        return JSONResponse({"detail": "Invalid bearer token"}, status_code=401)
    return await call_next(request)


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router)
app.mount("/mcp", mcp_app, name="mcp")

dist = Path(__file__).parent / "static"
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = dist / path
        return FileResponse(candidate if candidate.is_file() else dist / "index.html")
else:

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": "TaskRelay", "docs": "/docs"}
