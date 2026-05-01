# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем системные зависимости:
# 1. espeak-ng — основной движок для работы phonemizer
# 2. tesseract-ocr — для распознавания текста на фото (уже был)
RUN apt-get update && apt-get install -y \
    espeak-ng \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл с зависимостями Python
COPY requirements.txt .

# Устанавливаем Python-пакеты
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код бота
COPY . .

# Запускаем бота
CMD ["python", "bot.py"]

ENV PHONEMIZER_ESPEAK_LIBRARY=/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1
