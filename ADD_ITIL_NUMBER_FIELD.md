# ✅ Добавлено поле "Номер ITIL"

## 📋 Что сделано:

### 1. **Модель Task** (`app/tasks/models.py`)
Добавлено новое поле:
```python
itil_number = models.CharField(
    max_length=100,
    null=True,
    blank=True,
    verbose_name="Номер ITIL",
    help_text="Номер инцидента/заявки в ITIL системе"
)
```

### 2. **Формы** (`app/tasks/forms.py`)
Поле добавлено в формы:
- ✅ **TaskForm** — форма создания задачи
- ✅ **TaskEditForm** — форма редактирования задачи

Настройки:
- Виджет: TextInput с placeholder "Например: INC0012345"
- Label: "Номер ITIL"
- Поле необязательное (required=False)

### 3. **Админка** (`app/tasks/admin.py`)
- ✅ Добавлено в `list_display` — отображается в списке задач
- ✅ Добавлено в `search_fields` — можно искать по номеру ITIL
- ✅ Добавлено в `fieldsets` — доступно при редактировании

### 4. **Шаблоны**

**task_detail.html:**
```html
<p class="mb-1"><strong>Номер ITIL:</strong> 
    {% if task.itil_number %}
        <span class="badge bg-success">{{ task.itil_number }}</span>
    {% else %}
        <span class="text-muted">Не указан</span>
    {% endif %}
</p>
```

**task_list.html:**
```html
<li class="list-group-item d-flex justify-content-between align-items-center">
    Номер ITIL: 
    {% if task.itil_number %}
        <span class="badge bg-success">{{ task.itil_number }}</span>
    {% else %}
        <span class="text-muted">Не указан</span>
    {% endif %}
</li>
```

---

## 🚀 Создание и применение миграции:

### ⚠️ ВАЖНО: Необходимо создать миграцию!

Выполните команды:

```bash
# Создать миграцию
docker exec django_task_tracker python manage.py makemigrations

# Применить миграцию
docker exec django_task_tracker python manage.py migrate
```

**Ожидаемый результат:**
```
Migrations for 'tasks':
  tasks/migrations/0014_task_itil_number.py
    - Add field itil_number to task
```

---

## 📝 Где отображается поле:

### 1. **Форма создания задачи** (`/tasks/create/`)
- Поле "Номер ITIL" с placeholder
- Необязательное для заполнения

### 2. **Форма редактирования задачи** (`/tasks/<id>/` - для менеджеров)
- Поле "Номер ITIL" можно редактировать

### 3. **Детали задачи** (`/tasks/<id>/`)
- В блоке информации о задаче
- Отображается с зеленым бейджем если заполнено

### 4. **Список задач** (`/tasks/`)
- В карточке каждой задачи
- Между "Актив" и "Срок"

### 5. **Django Admin** (`/admin/tasks/task/`)
- В списке задач (колонка)
- В форме редактирования
- Доступен поиск по номеру ITIL

---

## 🎯 Использование:

### Пример заполнения:
- `INC0012345` — инцидент ITIL
- `REQ0098765` — запрос в ITIL
- `CHG0001234` — изменение в ITIL
- Любой текст до 100 символов

### Поиск в админке:
1. Перейти в `/admin/tasks/task/`
2. В поле поиска ввести номер: `INC0012345`
3. Найдутся все задачи с этим номером

---

## 🔄 Отличие от external_id:

| Поле | Назначение | Видимость |
|------|-----------|-----------|
| **itil_number** | Для ручного ввода номера ITIL пользователем | Везде видно в интерфейсе |
| **external_id** | Для автоматической синхронизации (отключено) | Скрыто, только в админке |

---

**Дата добавления:** 2025-10-16  
**Автор:** Добавлено по запросу пользователя



