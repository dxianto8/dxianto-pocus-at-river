FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# DEV=true (set by docker-compose.yml) adds pytest, ruff and Playwright's Chromium for running tests.
ARG DEV=false
COPY requirements.txt requirements-dev.txt ./
RUN if [ "$DEV" = "true" ]; then \
      pip install -r requirements-dev.txt && playwright install --with-deps chromium; \
    else \
      pip install -r requirements.txt; \
    fi

COPY . .

# Collect static files at build time. The values here exist only so settings can load.
RUN DJANGO_SECRET_KEY=build-only DATABASE_URL=postgres://build@localhost/build \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Apply any new migrations, then serve. Hosts like Render set $PORT.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 3 --access-logfile -"]
