FROM python:3.12-slim

ARG BYOS_REVISION=10d16d73f696a26cc9843456adbd558fb4699d91

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium git patch \
    && git clone https://github.com/usetrmnl/byos_fastapi.git /app \
    && git -C /app checkout "${BYOS_REVISION}" \
    && rm -rf /app/.git

COPY 400x300-display.patch /tmp/400x300-display.patch

RUN cd /app \
    && patch -p1 < /tmp/400x300-display.patch \
    && rm /tmp/400x300-display.patch \
    && pip install --no-cache-dir -r /app/requirements.txt \
    && apt-get purge -y --auto-remove git patch \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/var \
    && chown -R 1000:1000 /app

USER 1000:1000
WORKDIR /app
EXPOSE 4567

CMD ["python", "-u", "-m", "trmnl_server"]
