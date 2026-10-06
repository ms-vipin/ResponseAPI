FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    --index-url https://packagefeedproxy.microsoft.io/pypi/simple uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable

EXPOSE 8000

CMD ["uvicorn", "responseapi.mcp_bearer:app", "--host", "0.0.0.0", "--port", "8000"]