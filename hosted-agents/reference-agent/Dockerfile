FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    --index-url https://packagefeedproxy.microsoft.io/pypi/simple uv

COPY pyproject.toml uv.lock uv.toml ./
COPY main.py ./

RUN uv sync --frozen --no-dev --no-editable

CMD ["python", "main.py"]