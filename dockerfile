FROM python:3.11-slim

# Установка системных зависимостей: eSpeak-ng для phonemizer, Tesseract для OCR
RUN apt-get update && apt-get install -y \
    espeak-ng \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
