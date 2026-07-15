# Dashboard container: precomputed results are baked in; the app only reads.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY config/ config/
COPY src/ src/
COPY data/sample/ data/sample/
COPY outputs/ outputs/
RUN uv sync --frozen --no-dev

EXPOSE 8501
CMD ["uv", "run", "streamlit", "run", "src/dashboard/app.py", "--server.address=0.0.0.0", "--server.headless=true"]
