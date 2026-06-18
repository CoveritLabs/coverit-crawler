FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts

RUN python -m pip install --upgrade pip && python -m pip install --no-cache-dir --extra-index-url https://coveritlabs.github.io/coverit-contracts/simple/ . && python -m playwright install --with-deps chromium

CMD ["python", "-m", "arq", "src.workers.main.WorkerSettings"]
