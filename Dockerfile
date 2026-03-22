FROM python:3.12-slim AS base

WORKDIR /app
COPY . .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV HOST=0.0.0.0

EXPOSE 8000

FROM base AS prod

RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app

USER appuser
CMD ["python", "app.py"]

# --- Development stage: adds watchmedo for hot reload ---
FROM base AS dev

RUN pip install --no-cache-dir "watchdog[watchmedo]"

ENV WATCHDOG_FORCE_POLLING=true
ENV WATCHDOG_POLLING_INTERVAL=1

CMD ["watchmedo", "auto-restart", \
     "--debug-force-polling", \
     "--interval=1", \
     "--patterns=*.py;*.html;*.js;*.css;*.json", \
     "--recursive", \
     "--", \
     "python", "app.py"]
