FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# Dependencies only; the source tree is bind-mounted at /app by docker-compose.yml.
COPY pyproject.toml /tmp/pyproject.toml
RUN python -c "import tomllib; p = tomllib.load(open('/tmp/pyproject.toml', 'rb'))['project']; o = p['optional-dependencies']; print('\n'.join(p['dependencies'] + o['providers'] + o['dev']))" > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt /tmp/pyproject.toml

# Tool caches stay out of the bind-mounted source tree.
ENV RUFF_CACHE_DIR=/tmp/ruff-cache \
    MYPY_CACHE_DIR=/tmp/mypy-cache

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin covenant \
    && chown covenant /app
USER 10001

EXPOSE 8000
