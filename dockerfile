FROM python:3.11-slim

# Устанавливаем eSpeak-ng и Tesseract (для распознавания фото)
RUN apt-get update && apt-get install -y \
    espeak-ng \
    libespeak-ng-dev \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
