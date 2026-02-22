FROM python:3.14.3-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MCP_TRANSPORT=streamable-http \
    FASTMCP_HOST=0.0.0.0 \
    FASTMCP_PORT=8550

WORKDIR /app

# Install the package and its dependencies
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --upgrade pip && \
    pip install .

# Run as non-root
RUN useradd -m appuser
USER appuser

EXPOSE 8550

CMD ["dataverse-mcp-server"]
