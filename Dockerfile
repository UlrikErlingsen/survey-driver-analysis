FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    ARROW_DEFAULT_MEMORY_POOL=system

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 driversignal \
    && chown -R driversignal:driversignal /app
USER driversignal

EXPOSE 8594

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8594/_stcore/health', timeout=3)"

CMD ["python", "-m", "streamlit", "run", "app.py", "--server.headless=true", "--server.address=0.0.0.0", "--server.port=8594", "--browser.gatherUsageStats=false"]
