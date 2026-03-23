FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt \
    && playwright install chromium

COPY src /app/src
COPY scenarios /app/scenarios
COPY templates /app/templates
COPY README.md /app/README.md

CMD ["python", "-m", "src.run_tests"]
