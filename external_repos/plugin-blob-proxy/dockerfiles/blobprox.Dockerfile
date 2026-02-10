FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN useradd -r -s /bin/false appuser && \
    mkdir -p /app && \
    chown -R appuser:appuser /app

WORKDIR /app

COPY pyproject.toml src/ ./
RUN pip install .

USER appuser
CMD ["uvicorn", "blobprox.main:app", "--host", "0.0.0.0", "--port", "8082"]
