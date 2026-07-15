FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app:/app/agent-server

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY agent-server/requirements.txt /tmp/agent-requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /tmp/agent-requirements.txt

COPY shared /app/shared
COPY agent-server /app/agent-server
WORKDIR /app/agent-server
RUN mkdir -p artifacts

EXPOSE 8010

# One worker keeps each LangGraph thread ordered. Scale the service as a unit
# only after replacing any remaining in-process state with a shared checkpointer.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*", "--timeout-keep-alive", "120", "--no-access-log"]
