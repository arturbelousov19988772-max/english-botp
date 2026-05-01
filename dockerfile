FROM python:3.11-slim

# Установка системных зависимостей для Tesseract и epitran
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-rus \
    gcc \
    g++ \
    make \
    python3-dev \
    libicu-dev \
    pkg-config \
    flite \
    flite-dev \
    && rm -rf /var/lib/apt/lists/*

# Установка переменных окружения для увеличения таймаутов
ENV REQUESTS_TIMEOUT=120
ENV OCR_SPACE_TIMEOUT=120

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
