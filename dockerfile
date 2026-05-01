FROM python:3.11-slim

# Установка всех системных зависимостей для Tesseract и epitran
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
    libflite1 \
    libflite-dev \
    git \
    cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Дополнительная установка epitran с поддержкой flite
RUN pip install --no-cache-dir epitran --upgrade

COPY . .

CMD ["python", "bot.py"]
