"""Entry point for pluginlake FastAPI service (`python -m pluginlake`)."""

import os

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="pluginlake")


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    host = os.environ.get("PLUGINLAKE_HOST", "0.0.0.0")  # noqa: S104
    port = int(os.environ.get("PLUGINLAKE_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
