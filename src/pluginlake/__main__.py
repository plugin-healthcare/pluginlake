"""Entry point for pluginlake FastAPI service (`python -m pluginlake`)."""

import uvicorn
from fastapi import FastAPI

from pluginlake.config import ServerSettings

app = FastAPI(title="pluginlake")


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    server = ServerSettings()
    uvicorn.run(app, host=server.host, port=server.port)
