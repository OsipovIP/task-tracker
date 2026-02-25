#!/bin/bash
# Скрипт для импорта проекта Task Tracker на новую машину

echo "🚀 Импорт проекта Task Tracker..."

# Проверка наличия файлов
if [ ! -f "task_tracker_image.tar" ]; then
    echo "❌ Файл task_tracker_image.tar не найден!"
    exit 1
fi

if [ ! -f "task_tracker_source.tar.gz" ]; then
    echo "❌ Файл task_tracker_source.tar.gz не найден!"
    exit 1
fi

# 1. Распаковка исходного кода
echo "📄 Распаковка исходного кода..."
tar -xzf task_tracker_source.tar.gz

# 2. Загрузка Docker образа
echo "🐳 Загрузка Docker образа..."
docker load -i task_tracker_image.tar

# 3. Запуск контейнеров
echo "🚀 Запуск контейнеров..."
docker-compose up -d

# Ожидание запуска базы данных
echo "⏳ Ожидание запуска базы данных..."
sleep 10

# 4. Восстановление базы данных (если есть дамп)
if [ -f "task_tracker_dump.sql" ]; then
    echo "💾 Восстановление базы данных..."
    docker exec -i django_task_tracker psql -U postgres -d task_tracker < task_tracker_dump.sql
fi

# 5. Восстановление медиафайлов (если есть)
if [ -f "media_data.tar.gz" ]; then
    echo "📁 Восстановление медиафайлов..."
    tar -xzf media_data.tar.gz
fi

# 6. Применение миграций
echo "🔄 Применение миграций..."
docker exec django_task_tracker python manage.py migrate

# 7. Сбор статических файлов
echo "📦 Сбор статических файлов..."
docker exec django_task_tracker python manage.py collectstatic --noinput

echo "✅ Импорт завершен!"
echo "🌐 Приложение доступно по адресу: http://localhost:7575/"
echo "🔧 Админка: http://localhost:7575/admin/"
