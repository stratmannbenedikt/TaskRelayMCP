from taskrelaymcp.app import app


def main() -> None:
    import uvicorn

    uvicorn.run("taskrelaymcp.app:app", host="0.0.0.0", port=8080)


__all__ = ["app", "main"]
