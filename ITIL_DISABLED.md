# ⚠️ ITIL функционал отключен

## 📋 Что было отключено:

### 1. **Views (логика)**
**Файл:** `app/tasks/views.py`
- Строка 15: Убрана логика загрузки ITIL задач
- Строки 86-90: Закомментирован доступ к ITIL задачам без исполнителя

### 2. **Шаблоны (интерфейс)**

**Файл:** `app/tasks/templates/tasks/task_list.html`
- Строки 44-51: Закомментирован бейдж ITIL

**Файл:** `app/tasks/templates/tasks/task_detail.html`
- Строки 29-35: Закомментирован бейдж ITIL в заголовке
- Строки 41-66: Закомментирован блок с данными из ITIL системы
- Строка 71: Изменен default для репортера
- Строки 251-259: Закомментирована проверка ITIL для изменения статуса
- Строки 280-288: Закомментирована проверка ITIL для загрузки фото

**Файл:** `app/tasks/templates/tasks/work_order_management.html`
- Строки 57-61: Закомментирован бейдж ITIL в таблице

### 3. **Админка**
**Файл:** `app/tasks/admin.py`
- Строка 34: Убрано `external_source` из `list_display`
- Строка 35: Убрано `external_source` из `list_filter`
- Строка 36: Убрано `external_id` из `search_fields`
- Строки 52-57: Секция "Внешняя интеграция" переименована в "Внешняя интеграция (ОТКЛЮЧЕНО)"

---

## ✅ Что осталось без изменений:

### 1. **Модель Task**
**Файл:** `app/tasks/models.py`
- Поля `external_source`, `external_id`, `external_data` **сохранены в базе данных**
- Уникальное ограничение `unique_external_task` **активно**
- **Причина:** Поля могут содержать данные, их удаление потребует миграции

### 2. **Команда синхронизации**
**Файл:** `app/tasks/management/commands/sync_itil_incidents.py`
- Команда **НЕ удалена**, просто не используется
- **Причина:** Может понадобиться в будущем

### 3. **Документация**
**Файл:** `ITIL_INTEGRATION.md`
- Документация **сохранена** для справки

---

## 🔄 Как включить ITIL обратно:

### 1. Раскомментировать код в views.py:
```python
# Строка 15
# ITIL функционал отключен
# → заменить на: # Включаем как обычные задачи, так и ITIL задачи

# Строки 86-90
user_can_work = (
    task.assigned_to == request.user or 
    task.reporter == request.user
    # or (task.external_source == 'ITIL' and not task.assigned_to)  # ITIL отключен
)
# → раскомментировать последнюю строку
```

### 2. Раскомментировать блоки в шаблонах:

**task_list.html:** Удалить `{% comment %}` и `{% endcomment %}` вокруг строк 45-50

**task_detail.html:** Удалить все `{% comment %} ITIL ОТКЛЮЧЕНО` и `{% endcomment %}`

**work_order_management.html:** Удалить `{% comment %}` и `{% endcomment %}` вокруг строк 57-61

### 3. Вернуть поля в админке (admin.py):

```python
# Строка 34
list_display = ('id', 'title', 'status', 'priority', 'reporter', 'assigned_to', 'external_source', 'created_at')

# Строка 35
list_filter = ('status', 'priority', 'external_source', 'created_at')

# Строка 36
search_fields = ('title', 'description', 'reporter__username', 'assigned_to__username', 'external_id')

# Строка 53
('Внешняя интеграция', {
    'fields': ('external_source', 'external_id', 'external_data'),
    'classes': ('collapse',),
    'description': 'Данные из внешних систем (ITIL, Jira, etc.)'
}),
```

### 4. Запустить синхронизацию:

```bash
docker exec django_task_tracker python manage.py sync_itil_incidents \
  --username osipovip \
  --password HOW45h05 \
  --service-filter "Поддержка УАПП"
```

### 5. Настроить автоматическую синхронизацию (cron):

```bash
# Редактировать crontab
crontab -e

# Добавить строку (каждые 30 минут)
*/30 * * * * docker exec django_task_tracker python manage.py sync_itil_incidents --username osipovip --password HOW45h05
```

---

## 📊 Что изменится при включении:

1. ✅ ITIL задачи будут отображаться с зеленым бейджем "ITIL"
2. ✅ Данные из ITIL системы будут видны в карточке задачи
3. ✅ ITIL задачи без исполнителя можно будет редактировать
4. ✅ В админке будет фильтр по `external_source`
5. ✅ Автоматическая синхронизация инцидентов из ITIL API

---

## 🗄️ База данных

**Важно:** Существующие ITIL задачи **НЕ удалены** из базы данных. Они просто:
- Не отображаются с ITIL бейджами
- Не имеют специальной логики доступа
- Работают как обычные задачи

Чтобы найти ITIL задачи в БД:
```python
# В Django shell
from tasks.models import Task
itil_tasks = Task.objects.filter(external_source='ITIL')
print(f"Найдено ITIL задач: {itil_tasks.count()}")
```

---

**Дата отключения:** 2025-10-16  
**Причина:** Не требуется интеграция с ITIL системой



