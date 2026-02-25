# Интеграция с ITIL системой

## 📋 Общая концепция

ITIL инциденты автоматически импортируются как **полноценные задачи (Task)** в систему учета работ. Это позволяет не переносить задачи вручную и работать с ними в едином интерфейсе.

## 🔑 Ключевые особенности

### 1. **Предотвращение дублирования**
Каждая задача имеет поля:
- `external_source` = "ITIL" — источник задачи
- `external_id` — уникальный ID инцидента из ITIL
- `external_data` — полные исходные данные из ITIL (JSON)

Уникальность гарантируется ограничением базы данных: одна комбинация `(external_source, external_id)` может быть только один раз.

### 2. **Автоматический маппинг данных**

#### Приоритет:
- **Критический** (ITIL) → `critical` (Task)
- **Высокий** → `high`
- **Средний** → `medium`
- **Низкий** → `low`

#### Статус:
- **Зарегистрирован** → `todo` (К выполнению)
- **Принят к выполнению** → `in_progress` (В работе)
- **Эскалация** → `waiting` (Ожидание)
- **Выполнен/Закрыт** → `done` (Выполнено)

### 3. **Возможность дозаполнения**

После импорта ITIL задачи можно **редактировать**:
- ✅ Назначить исполнителя вручную
- ✅ Изменить статус
- ✅ Добавить связь с оборудованием (OES Object)
- ✅ Изменить приоритет
- ✅ Добавить комментарии и фото
- ✅ Установить срок выполнения

**Важно:** Поля `external_source`, `external_id`, `external_data` доступны только для чтения.

## 🔄 Синхронизация

### Команда для синхронизации:

```bash
docker exec django_task_tracker python manage.py sync_itil_incidents \
    --username osipovip \
    --password HOW45h05
```

### Параметры команды:

- `--url` — URL ITIL API (по умолчанию: `http://1c02-app01/IT_ITIL/hs/api/v1/incident/`)
- `--username` — Имя пользователя для авторизации
- `--password` — Пароль
- `--token` — Bearer токен (альтернатива username/password)
- `--service-filter` — Фильтр по услуге (по умолчанию: "Поддержка УАПП")
- `--dry-run` — Режим тестирования без сохранения
- `--try-alternative-urls` — Попробовать разные варианты URL

### Автоматизация синхронизации:

Для регулярного обновления можно настроить cron:

```cron
# Каждые 30 минут
*/30 * * * * docker exec django_task_tracker python manage.py sync_itil_incidents --username osipovip --password HOW45h05

# Каждый час
0 * * * * docker exec django_task_tracker python manage.py sync_itil_incidents --username osipovip --password HOW45h05

# Каждые 15 минут
*/15 * * * * docker exec django_task_tracker python manage.py sync_itil_incidents --username osipovip --password HOW45h05
```

## 📊 Отображение в интерфейсе

### Веб-интерфейс:
- ITIL задачи отображаются в едином списке с обычными задачами
- ITIL задачи помечены зеленым бейджем "ITIL" 
- Видны все задачи, назначенные пользователю
- Можно кликнуть на задачу для просмотра деталей
- В деталях задачи показываются исходные данные из ITIL системы

### Django Admin:
- В списке задач ITIL задачи помечены в колонке "External Source"
- Фильтр по "External Source" позволяет показать только ITIL задачи
- При редактировании ITIL задачи исходные данные доступны в разделе "Внешняя интеграция"

## 🔧 Технические детали

### Модель Task:
```python
class Task(models.Model):
    # ... стандартные поля ...
    
    # Поля для интеграции
    external_source = models.CharField(max_length=50, null=True, blank=True)
    external_id = models.CharField(max_length=100, null=True, blank=True)
    external_data = models.JSONField(null=True, blank=True)
```

### Логика синхронизации:
1. Подключение к ITIL API через NTLM авторизацию
2. Получение списка инцидентов
3. Фильтрация по услуге "Поддержка УАПП"
4. Для каждого инцидента:
   - Проверка существования задачи по `(external_source='ITIL', external_id=incident_id)`
   - Если существует → **обновление** данных
   - Если не существует → **создание** новой задачи
5. Сохранение исходных данных в `external_data`

## ⚠️ Важные замечания

1. **Не удаляйте задачи вручную** — при следующей синхронизации они будут созданы заново
2. **Для "архивации" ITIL задач** — измените статус на "Выполнено"
3. **Исходные данные из ITIL** хранятся в поле `external_data` и доступны для просмотра
4. **Timezone warnings** — это предупреждения о датах без timezone, не критично

## 📝 Примеры использования

### Проверка ITIL задач:
```bash
docker exec django_task_tracker python manage.py shell -c \
  "from tasks.models import Task; print(f'ITIL задач: {Task.objects.filter(external_source=\"ITIL\").count()}')"
```

### Тестовый запуск (без сохранения):
```bash
docker exec django_task_tracker python manage.py sync_itil_incidents \
    --username osipovip \
    --password HOW45h05 \
    --dry-run
```

### Просмотр деталей ITIL задачи:
```bash
docker exec django_task_tracker python manage.py shell -c \
  "from tasks.models import Task; import json; t = Task.objects.filter(external_source='ITIL').first(); print(json.dumps(t.external_data, indent=2, ensure_ascii=False))"
```

## 🎯 Workflow для работы с ITIL задачами

1. **Автоматический импорт** — задачи создаются автоматически
2. **Назначение исполнителя** — через админку или в веб-интерфейсе
3. **Работа над задачей** — добавление комментариев, фото, изменение статуса
4. **Связь с оборудованием** — при необходимости связать с OES объектом
5. **Завершение** — установка статуса "Выполнено"

### 🔧 Особенности редактирования ITIL задач:

- **Без назначенного исполнителя:** Любой пользователь может редактировать
- **С назначенным исполнителем:** Только назначенный исполнитель может редактировать
- **Создатель задачи:** Всегда может редактировать свою задачу

---

**Контакты для вопросов:** Администратор системы

