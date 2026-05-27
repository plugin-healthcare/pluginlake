"""Entry point for pluginlake FastAPI service (`python -m pluginlake`)."""

import uvicorn

from pluginlake.api.app import create_app
from pluginlake.config import ServerSettings

app = create_app()

if __name__ == "__main__":
    server = ServerSettings()
    uvicorn.run(
        "pluginlake.__main__:app",
        host=server.host,
        port=server.port,
        workers=server.workers,
        limit_concurrency=server.limit_concurrency,
        timeout_keep_alive=server.timeout_keep_alive,
    )
