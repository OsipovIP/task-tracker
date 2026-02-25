# task_tracker_project/Dockerfile
# Используем официальный образ Python
FROM python:3.11-slim

# Установка рабочей директории в контейнере
WORKDIR /usr/src/app

# Установка системных зависимостей для psycopg2-binary
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копирование и установка зависимостей Python
COPY ./app/requirements.txt .
RUN pip install \
    --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --timeout 1000 \
    -r requirements.txt

# Копирование всего кода приложения
COPY ./app .

# Копирование Telegram бота
COPY ./telegram_bot ./telegram_bot

# Установка переменной окружения, чтобы Python сразу видел, что используется Docker
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Запуск будет настроен через docker-compose.yml