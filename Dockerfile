# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.13.16-alpine@sha256:2d9aefe2fef018a7eb2c13064c89c71929800fd2e5dccdbf52ea5da5bb8d929a
FROM ${PYTHON_IMAGE} AS builder

RUN --mount=type=secret,id=build_ca \
    cp /etc/ssl/certs/ca-certificates.crt /tmp/original-ca.pem && \
    if [ -s /run/secrets/build_ca ]; then cat /run/secrets/build_ca >> /etc/ssl/certs/ca-certificates.crt; fi && \
    apk add --no-cache patch && apk upgrade --no-cache && \
    cp /tmp/original-ca.pem /etc/ssl/certs/ca-certificates.crt && rm /tmp/original-ca.pem
COPY docker/patches /patches
RUN cd /usr/local/lib/python3.13 && \
    patch -p2 < /patches/CVE-2025-15367.patch && \
    patch -p2 < /patches/CVE-2026-12345.patch && \
    patch -p2 < /patches/CVE-2026-12345-nofollow.patch
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN --mount=type=secret,id=build_ca \
    cp /etc/ssl/certs/ca-certificates.crt /tmp/build-ca.pem && \
    if [ -s /run/secrets/build_ca ]; then cat /run/secrets/build_ca >> /tmp/build-ca.pem; fi && \
    PIP_CERT=/tmp/build-ca.pem pip install --no-cache-dir uv==0.12.23 && \
    SSL_CERT_FILE=/tmp/build-ca.pem uv sync --frozen --no-dev --no-editable

FROM ${PYTHON_IMAGE}
WORKDIR /app
RUN --mount=type=secret,id=build_ca \
    cp /etc/ssl/certs/ca-certificates.crt /tmp/original-ca.pem && \
    if [ -s /run/secrets/build_ca ]; then cat /run/secrets/build_ca >> /etc/ssl/certs/ca-certificates.crt; fi && \
    apk upgrade --no-cache && \
    apk add --no-cache 'zlib>=1.3.2-r1' alpine-baselayout-data ca-certificates-bundle && \
    cp /tmp/original-ca.pem /etc/ssl/certs/ca-certificates.crt && rm /tmp/original-ca.pem && \
    python -m pip uninstall -y pip && \
    apk del --no-network ca-certificates alpine-baselayout busybox busybox-binsh ssl_client && \
    python -c "import os; os.makedirs('/tmp', exist_ok=True); os.chmod('/tmp', 0o1777)"
COPY --from=builder /usr/local/lib/python3.13/poplib.py /usr/local/lib/python3.13/poplib.py
COPY --from=builder /usr/local/lib/python3.13/shutil.py /usr/local/lib/python3.13/shutil.py
COPY --from=builder /usr/local/lib/python3.13/tempfile.py /usr/local/lib/python3.13/tempfile.py
COPY --from=builder /app/.venv /app/.venv
COPY LICENSE ./LICENSE
COPY scripts/validate_remote.py ./scripts/validate_remote.py
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
EXPOSE 8443
CMD ["jamf-mcp", "--read-only"]
