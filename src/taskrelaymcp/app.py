from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from taskrelaymcp.api import router
from taskrelaymcp.auth import authenticate_mcp
from taskrelaymcp.db import init_db, session_scope
from taskrelaymcp.mcp_server import mcp

mcp_app = mcp.http_app(path="/", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    async with mcp_app.lifespan(app):
        yield


app = FastAPI(title="TaskRelay", version="0.5.0", lifespan=lifespan)


@app.middleware("http")
async def protect_mcp(request: Request, call_next):
    if request.url.path.startswith("/mcp"):
        with session_scope() as db:
            if not authenticate_mcp(db, request.headers.get("authorization")):
                return JSONResponse({"detail": "Invalid or revoked MCP key"}, status_code=401)
    return await call_next(request)


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router)
app.mount("/mcp", mcp_app, name="mcp")


@app.get("/api/{path:path}", include_in_schema=False)
def missing_api(path: str) -> JSONResponse:
    return JSONResponse({"detail": "Not Found"}, status_code=404)


dist = Path(__file__).parent / "static"
if dist.exists():
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = dist / path
        return FileResponse(candidate if candidate.is_file() else dist / "index.html")
else:

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": "TaskRelay", "docs": "/docs"}
