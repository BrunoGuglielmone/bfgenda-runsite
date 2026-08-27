FROM debian:bookworm-slim AS litestream

ARG LITESTREAM_VERSION=0.5.16
ARG LITESTREAM_SHA256=9e29112380a942e4a62ee07773684396cb8b308dc4d67e130bef41f75e937f0a

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL \
        "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-x86_64.tar.gz" \
        -o /tmp/litestream.tar.gz \
    && echo "${LITESTREAM_SHA256}  /tmp/litestream.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/litestream.tar.gz -C /usr/local/bin litestream

FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY --from=litestream /usr/local/bin/litestream /usr/local/bin/litestream

COPY requirements.txt ./
RUN python -m pip install -r requirements.txt

COPY . .
RUN AGENDE_DEBUG=0 python manage.py collectstatic --noinput

EXPOSE 8080

CMD ["python", "scripts/iniciar_runsite_con_litestream.py"]
