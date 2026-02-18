"""Entry point for pluginlake FastAPI service (`python -m pluginlake`)."""

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="pluginlake")


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)
