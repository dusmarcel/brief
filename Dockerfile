FROM python:3.12-slim AS runtime

WORKDIR /app
COPY . .

ENV PORT=8000
ENV HOST=0.0.0.0

EXPOSE 8000
CMD ["python", "app.py"]

# --- Development stage: adds watchmedo for hot reload ---
FROM runtime AS dev

RUN pip install --no-cache-dir "watchdog[watchmedo]"

CMD ["watchmedo", "auto-restart", \
     "--patterns=*.py;*.html;*.js;*.css;*.json", \
     "--recursive", \
     "--", \
     "python", "app.py"]
