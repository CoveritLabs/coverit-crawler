FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml uv.lock requirements.runtime.txt README.md ./
RUN python -m pip install -r requirements.runtime.txt

COPY src ./src
COPY scripts ./scripts

RUN python -m pip install --no-deps .

CMD ["python", "-m", "arq", "src.workers.main.WorkerSettings"]
