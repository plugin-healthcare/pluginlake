"""Entry point for pluginlake FastAPI service (`python -m pluginlake`)."""

import uvicorn

from pluginlake.api.app import create_app
from pluginlake.config import ServerSettings

app = create_app()

if __name__ == "__main__":
    server = ServerSettings()
    uvicorn.run(app, host=server.host, port=server.port)
