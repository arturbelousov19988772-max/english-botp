FROM python:3.11-slim

# Устанавливаем espeak-ng (обязательно для phonemizer) и tesseract (для фото)
RUN apt-get update && apt-get install -y \
    espeak-ng \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

# Опционально: указать путь к библиотеке espeak-ng (на всякий случай)
ENV PHONEMIZER_ESPEAK_LIBRARY=/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
