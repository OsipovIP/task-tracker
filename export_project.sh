#!/bin/bash
# Скрипт для экспорта проекта Task Tracker

echo "🚀 Экспорт проекта Task Tracker..."

# 1. Остановка контейнеров
echo "📦 Остановка контейнеров..."
docker-compose down

# 2. Создание дампа базы данных
echo "💾 Создание дампа базы данных..."
docker run --rm -v task_tracker_project_pgdata:/var/lib/postgresql/data -v $(pwd):/backup postgres:13 pg_dump -U postgres -d task_tracker > task_tracker_dump.sql

# 3. Экспорт Docker образа
echo "🐳 Экспорт Docker образа..."
docker save django-init-image:latest -o task_tracker_image.tar

# 4. Архивирование медиафайлов
echo "📁 Архивирование медиафайлов..."
tar -czf media_data.tar.gz media_data/

# 5. Архивирование исходного кода
echo "📄 Архивирование исходного кода..."
tar -czf task_tracker_source.tar.gz \
  app/ \
  docker-compose.yml \
  Dockerfile \
  .env \
  *.md \
  *.sh

echo "✅ Экспорт завершен!"
echo "📦 Созданные файлы:"
echo "   - task_tracker_image.tar (Docker образ)"
echo "   - task_tracker_source.tar.gz (исходный код)"
echo "   - task_tracker_dump.sql (дамп БД)"
echo "   - media_data.tar.gz (медиафайлы)"
echo ""
echo "🚚 Перенесите эти файлы на новую машину"
