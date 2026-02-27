from django.db import models
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

User = get_user_model()

# =====================================================================
# --- МОДЕЛИ ДЛЯ OES (ВНЕШНИЕ ДАННЫЕ) ---
# Определены первыми, чтобы на них могли ссылаться последующие модели.
# =====================================================================

class OesCategory(models.Model):
    """Категория оборудования (например, 'Самосвал', 'Бульдозер')."""
    source_id = models.IntegerField(unique=True, help_text="ID категории из внешнего источника.")
    name = models.CharField(max_length=255, verbose_name="Название категории")

    class Meta:
        verbose_name = "Категория OES"
        verbose_name_plural = "Категории OES"

    def __str__(self):
        return self.name

class OesModel(models.Model):
    """Модель оборудования (например, 'Komatsu HD 1500-8 GalileoSky')."""
    source_id = models.IntegerField(unique=True, help_text="ID модели из внешнего источника.")
    category = models.ForeignKey(OesCategory, on_delete=models.CASCADE, related_name='models', verbose_name="Категория")
    name = models.CharField(max_length=255, verbose_name="Название модели")

    class Meta:
        verbose_name = "Модель OES"
        verbose_name_plural = "Модели OES"

    def __str__(self):
        return f"{self.category.name} / {self.name}"

class OesObject(models.Model):
    """Конкретный объект (единица техники, например, '0029')."""
    # Временно добавлен null=True для миграции существующих данных
    source_id = models.IntegerField(unique=True, help_text="ID объекта из внешнего источника.", null=True)
    
    # ИСПРАВЛЕНИЕ ОШИБКИ: Изменение related_name='objects' на related_name='oes_objects'
    # Это устраняет конфликт, когда обратный менеджер перезаписывал OesModel.objects.
    model = models.ForeignKey(
        OesModel, 
        on_delete=models.CASCADE, 
        related_name='oes_objects', # ИЗМЕНЕНО: было 'objects'
        verbose_name="Модель", 
        null=True
    )
    name = models.CharField(max_length=255, verbose_name="Название объекта")
    mdm_object_uuid = models.CharField(max_length=50, unique=True, verbose_name="MDM UUID", null=True)

    exclude_from_monitoring = models.BooleanField(
        default=False,
        verbose_name="Исключить из мониторинга",
        help_text="Консервация, списание, ремонт — не проверять телеметрию"
    )
    exclude_reason = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name="Причина исключения",
        help_text="Например: Консервация, Списан, В ремонте"
    )


    class Meta:
        verbose_name = "Объект OES"
        verbose_name_plural = "Объекты OES"

    def __str__(self):
        # Проверка, чтобы не вызвать ошибку, если model=None
        model_name = self.model.name if self.model else "Неизвестная модель"
        return f"{self.name} ({model_name})"

class OesObjectDevice(models.Model):
    """Устройство, привязанное к объекту."""
    # Временно добавлен null=True для миграции существующих данных
    source_id = models.IntegerField(unique=True, help_text="ID устройства из внешнего источника.", null=True)
    oes_object = models.ForeignKey(OesObject, on_delete=models.CASCADE, related_name='devices', verbose_name="Объект", null=True)
    source_object_id = models.CharField(max_length=255, unique=True, verbose_name="Внешний ID устройства")

    class Meta:
        verbose_name = "Устройство OES"
        verbose_name_plural = "Устройства OES"

    def __str__(self):
        # Проверка, чтобы не вызвать ошибку, если oes_object=None
        object_name = self.oes_object.name if self.oes_object else "Нет объекта"
        return f"Устройство {self.source_object_id} для {object_name}"


# =====================================================================
# --- МОДЕЛЬ ДЛЯ РУЧНОГО ВВОДА АКТИВОВ ---
# =====================================================================

class ManualAsset(models.Model):
    """Активы, которые можно заполнить вручную через админку для задач без OES."""
    name = models.CharField(max_length=255, verbose_name="Название актива")
    asset_type = models.CharField(max_length=100, verbose_name="Тип актива", help_text="Например: Техника, Оборудование, Транспорт")
    model = models.CharField(max_length=255, blank=True, verbose_name="Модель")
    description = models.TextField(blank=True, verbose_name="Описание")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Актив (ручной ввод)"
        verbose_name_plural = "Активы (ручной ввод)"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.asset_type})"


# =====================================================================
# --- ОСНОВНЫЕ МОДЕЛИ ЗАДАЧ ---
# =====================================================================

class Task(models.Model):
    # Приоритеты
    PRIORITY_CRITICAL = 'critical'
    PRIORITY_HIGH = 'high'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_LOW = 'low'
    PRIORITY_CHOICES = [
        (PRIORITY_CRITICAL, 'Критический'),
        (PRIORITY_HIGH, 'Высокий'),
        (PRIORITY_MEDIUM, 'Средний'),
        (PRIORITY_LOW, 'Низкий'),
    ]

    # Статусы
    STATUS_TODO = 'todo'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_WAITING = 'waiting'
    STATUS_CHECKING = 'checking'
    STATUS_DONE = 'done'
    STATUS_CHOICES = [
        (STATUS_TODO, 'К выполнению'),
        (STATUS_WAITING, 'Ожидание'),
        (STATUS_CHECKING, 'Проверка'),
        (STATUS_DONE, 'Выполнено'),
    ]

    # Основные поля задачи
    title = models.CharField(max_length=255, verbose_name="Заголовок")
    description = models.TextField(verbose_name="Описание", blank=True, default='')
    
    # Связи
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reported_tasks', verbose_name="Репортер (Создатель)", null=True, blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tasks', verbose_name="Личный исполнитель")
    assigned_group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name='group_tasks', verbose_name="Группа исполнителей")
    additional_assignees = models.ManyToManyField(User, blank=True, related_name='additional_tasks', verbose_name="Дополнительные исполнители")

    # Служебные поля
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TODO, verbose_name="Статус")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM, verbose_name="Приоритет")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    due_date = models.DateTimeField(null=True, blank=True, verbose_name="Срок")
    acknowledged_at = models.DateTimeField(null=True, blank=True, verbose_name="Подтверждена")
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата закрытия")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    # Связь с внешними объектами (OES)
    oes_object = models.ForeignKey(
        OesObject, 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name='tasks', 
        verbose_name="Связанный OES Объект"
    )
    
    # Связь с ручными активами
    manual_asset = models.ForeignKey(
        'ManualAsset',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='tasks',
        verbose_name="Ручной актив"
    )
    
    # Номер ITIL (для связи с внешними системами)
    itil_number = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Номер ITIL",
        help_text="Номер инцидента/заявки в ITIL системе"
    )
    
    # Поля для интеграции с внешними системами
    external_source = models.CharField(
        max_length=50, 
        null=True, 
        blank=True, 
        verbose_name="Внешний источник",
        help_text="Например: ITIL, Jira, etc."
    )
    external_id = models.CharField(
        max_length=100, 
        null=True, 
        blank=True, 
        verbose_name="Внешний ID",
        help_text="ID задачи во внешней системе"
    )
    external_data = models.JSONField(
        null=True, 
        blank=True, 
        verbose_name="Дополнительные данные",
        help_text="JSON с дополнительными данными из внешней системы"
    )

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ['-priority', 'due_date']
        # Уникальность по комбинации внешнего источника и ID (для предотвращения дублирования)
        constraints = [
            models.UniqueConstraint(
                fields=['external_source', 'external_id'],
                name='unique_external_task',
                condition=models.Q(external_source__isnull=False) & models.Q(external_id__isnull=False)
            )
        ]

    def __str__(self):
        return f"Task #{self.id}: {self.title}"

# --- Модель для комментариев ---
class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments', verbose_name="Задача")
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Автор")
    text = models.TextField(verbose_name="Текст комментария")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Комментарий к задаче"
        verbose_name_plural = "Комментарии к задаче"
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author.username} on Task #{self.task.id}"

# --- Модель для фотографий ---
class TaskPhoto(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='photos', verbose_name="Задача")
    image = models.ImageField(upload_to='task_photos/', verbose_name="Фотография", null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Загружено пользователем")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Фотография задачи"
        verbose_name_plural = "Фотографии задачи"

    def __str__(self):
        return f"Photo for Task #{self.task.id}"


# =====================================================================
# --- МОДЕЛИ ДЛЯ ОТЧЕТНОСТИ И ЗАКРЫТИЯ ЗАДАЧ ---
# =====================================================================

class FaultCategory(models.Model):
    """Категории неисправностей для структурирования отчетов о закрытии задач."""
    name = models.CharField(max_length=100, verbose_name="Название категории")
    description = models.TextField(blank=True, verbose_name="Описание")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")
    
    class Meta:
        verbose_name = "Категория неисправности"
        verbose_name_plural = "Категории неисправностей"
        ordering = ['sort_order', 'name']
    
    def __str__(self):
        return self.name

class TaskCompletionReport(models.Model):
    """Отчет исполнителя о выполненной работе при закрытии задачи."""
    task = models.OneToOneField(Task, on_delete=models.CASCADE, related_name='completion_report', verbose_name="Задача")
    completed_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Исполнитель")
    fault_category = models.ForeignKey(FaultCategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Категория неисправности")
    work_performed = models.TextField(verbose_name="Выполненная работа")
    root_cause = models.TextField(blank=True, verbose_name="Корневая причина")
    preventive_measures = models.TextField(blank=True, verbose_name="Предупредительные меры")
    time_spent = models.DurationField(null=True, blank=True, verbose_name="Затраченное время")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания отчета")
    
    class Meta:
        verbose_name = "Отчет о закрытии задачи"
        verbose_name_plural = "Отчеты о закрытии задач"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Отчет по задаче #{self.task.id} от {self.completed_by.username}"


# =====================================================================
# --- МОДЕЛИ ДЛЯ УЧЕТА РАЦИЙ ---
# =====================================================================

class RadioModel(models.Model):
    """Справочник моделей раций."""
    name = models.CharField(max_length=255, unique=True, verbose_name="Название модели")
    description = models.TextField(blank=True, verbose_name="Описание")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Модель рации"
        verbose_name_plural = "Модели раций"
        ordering = ['name']

    def __str__(self):
        return self.name


class RadioType(models.Model):
    """Справочник раций с техническими характеристиками."""
    model = models.ForeignKey(RadioModel, on_delete=models.PROTECT, related_name='radios', verbose_name="Модель")
    sn = models.CharField(max_length=100, unique=True, verbose_name="Серийный номер")
    ccid = models.CharField(max_length=100, blank=True, unique=True, null=True, verbose_name="CCID")
    sim = models.CharField(max_length=50, blank=True, unique=True, null=True, verbose_name="ID")
    description = models.TextField(blank=True, verbose_name="Описание")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Рация"
        verbose_name_plural = "Рации"
        ordering = ['model__name', 'sn']

    def __str__(self):
        return f"{self.model.name} (SN: {self.sn})"


class RadioAssignment(models.Model):
    """Выдача и возврат раций."""
    device = models.ForeignKey(RadioType, on_delete=models.CASCADE, related_name='assignments', verbose_name="Рация")
    assignee_name = models.CharField(max_length=255, verbose_name="Выдано кому", default='')
    department = models.CharField(max_length=255, verbose_name="Подразделение")
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='issued_radios', verbose_name="Выдал")
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата выдачи")
    returned_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата возврата")
    notes = models.TextField(blank=True, verbose_name="Примечания")
    pdf_file = models.FileField(upload_to='radio_assignments/', blank=True, null=True, verbose_name="PDF файл")

    class Meta:
        verbose_name = "Выдача рации"
        verbose_name_plural = "Выдачи раций"
        ordering = ['-issued_at']
        constraints = [
            # Запрещаем более одной активной (не возвращенной) выдачи на одну рацию
            models.UniqueConstraint(
                fields=['device'],
                condition=Q(returned_at__isnull=True),
                name='unique_open_assignment_per_device',
            )
        ]

    def __str__(self):
        return f"{self.device} → {self.assignee_name} ({self.issued_at})"
    
    @property
    def is_returned(self):
        """Проверка, возвращена ли рация."""
        return self.returned_at is not None


class RadioRepair(models.Model):
    """Учет ремонта раций."""
    device = models.ForeignKey(RadioType, on_delete=models.CASCADE, related_name='repairs', verbose_name="Рация")
    repair_date = models.DateTimeField(default=timezone.now, verbose_name="Дата ремонта")
    description = models.TextField(verbose_name="Описание работ")
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='radio_repairs', verbose_name="Выполнил")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания записи")

    class Meta:
        verbose_name = "Ремонт рации"
        verbose_name_plural = "Ремонты раций"
        ordering = ['-repair_date']

    def __str__(self):
        return f"Ремонт {self.device} от {self.repair_date}"
# =====================================================================
# --- МОДЕЛЬ ДЛЯ ХРАНЕНИЯ ПРОСТОЕВ (API idles) ---
# Добавить в конец файла models.py
# =====================================================================

class IdleRecord(models.Model):
    """Запись о простое техники, полученная из внешнего API."""
    
    # Внешний ID для защиты от дублей
    external_id = models.IntegerField(
        unique=True,
        verbose_name="ID простоя из API",
        help_text="Уникальный ID записи из внешнего API"
    )
    
    # Связь с техникой
    oes_object = models.ForeignKey(
        OesObject,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='idle_records',
        verbose_name="Объект OES"
    )
    object_uuid = models.UUIDField(
        null=True, blank=True,
        verbose_name="UUID объекта",
        help_text="object_uuid из API для связки с OesObject.mdm_object_uuid",
        db_index=True
    )
    object_id_external = models.IntegerField(
        null=True, blank=True,
        verbose_name="ID объекта из API",
        help_text="object_id из API"
    )
    
    # Временные рамки простоя
    begin_dt = models.DateTimeField(verbose_name="Начало простоя")
    end_dt = models.DateTimeField(null=True, blank=True, verbose_name="Конец простоя")
    duration = models.IntegerField(
        null=True, blank=True,
        verbose_name="Длительность (мин)"
    )
    duration_from_shift = models.IntegerField(
        null=True, blank=True,
        verbose_name="Длительность от смены (мин)"
    )
    
    # Классификация простоя
    idle_type_id = models.IntegerField(null=True, blank=True, verbose_name="ID типа простоя")
    idle_type_name = models.CharField(max_length=255, blank=True, default='', verbose_name="Тип простоя")
    category_id = models.IntegerField(null=True, blank=True, verbose_name="ID категории простоя")
    category_name = models.CharField(max_length=255, blank=True, default='', verbose_name="Категория простоя")
    
    # Дополнительные данные
    comment = models.TextField(blank=True, default='', verbose_name="Комментарий")
    selected = models.BooleanField(default=False, verbose_name="Выбран")
    is_manual = models.BooleanField(default=False, verbose_name="Ручной ввод")
    is_engine_on = models.BooleanField(default=False, verbose_name="Двигатель включён")
    is_allowed_zone = models.BooleanField(default=False, verbose_name="В разрешённой зоне")
    
    # Геолокация
    lat = models.CharField(max_length=50, blank=True, default='', verbose_name="Широта")
    lon = models.CharField(max_length=50, blank=True, default='', verbose_name="Долгота")
    geozones = models.CharField(max_length=500, blank=True, default='', verbose_name="Геозоны")
    
    # Служебные поля
    updated_by = models.CharField(max_length=255, blank=True, default='', verbose_name="Обновлено кем")
    enterprise_id = models.IntegerField(null=True, blank=True, verbose_name="ID предприятия")
    
    # Сырые данные (весь JSON ответ)
    raw_data = models.JSONField(null=True, blank=True, verbose_name="Сырые данные из API")
    
    # Метаданные импорта
    fetched_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")
    shift_type = models.CharField(
        max_length=10,
        choices=[('day', 'Дневная'), ('night', 'Ночная')],
        blank=True, default='',
        verbose_name="Тип смены"
    )

    class Meta:
        verbose_name = "Простой техники"
        verbose_name_plural = "Простои техники"
        ordering = ['-begin_dt']
        indexes = [
            models.Index(fields=['begin_dt', 'end_dt']),
            models.Index(fields=['object_uuid']),
            models.Index(fields=['category_name']),
        ]

    def __str__(self):
        obj_name = self.oes_object.name if self.oes_object else f"obj_{self.object_id_external}"
        return f"Простой {obj_name}: {self.begin_dt} - {self.category_name}"

        # =====================================================================
# --- ЭТАП 2: МОДЕЛИ ДЛЯ МОНИТОРИНГА ТЕЛЕМЕТРИИ ---
# Добавить в конец файла models.py
# =====================================================================

class ModelTagConfig(models.Model):
    """Конфигурация тегов для проверки телеметрии по модели техники.
    
    Определяет какие теги (колонки в ClickHouse) нужно проверять
    для каждой модели техники и каким способом.
    """
    
    # Типы проверки
    CHECK_EXISTS = 'exists'
    CHECK_THRESHOLD_MIN = 'threshold_min'
    CHECK_THRESHOLD_MAX = 'threshold_max'
    CHECK_THRESHOLD_RANGE = 'threshold_range'
    CHECK_CHANGE = 'change'
    CHECK_TYPE_CHOICES = [
        (CHECK_EXISTS, 'Наличие данных (значение ≠ -1000000)'),
        (CHECK_THRESHOLD_MIN, 'Минимальный порог (значение ≥ min)'),
        (CHECK_THRESHOLD_MAX, 'Максимальный порог (значение ≤ max)'),
        (CHECK_THRESHOLD_RANGE, 'Диапазон (min ≤ значение ≤ max)'),
        (CHECK_CHANGE, 'Изменение (значение должно меняться)'),
    ]
    
    # Таблицы ClickHouse
    CH_TABLE_TRUCKS = 'trucks'
    CH_TABLE_HEAVY = 'heavy_equipment'
    CH_TABLE_CHOICES = [
        (CH_TABLE_TRUCKS, 'Самосвалы (telemetry.trucks)'),
        (CH_TABLE_HEAVY, 'Тяжёлая техника (telemetry.heavy_equipment)'),
    ]
    
    # Связь с моделями техники (несколько моделей на один тег)
    oes_models = models.ManyToManyField(
        OesModel,
        related_name='tag_configs',
        verbose_name="Модели техники"
    )
    
    # Таблица ClickHouse
    clickhouse_table = models.CharField(
        max_length=50,
        choices=CH_TABLE_CHOICES,
        verbose_name="Таблица ClickHouse"
    )
    
    # Тег (колонка в ClickHouse)
    tag_name = models.CharField(
        max_length=100,
        verbose_name="Имя тега (колонка в ClickHouse)",
        help_text="Например: lon, lat, temp_engine, dut, speed_gps"
    )
    
    # Тип проверки
    check_type = models.CharField(
        max_length=20,
        choices=CHECK_TYPE_CHOICES,
        default=CHECK_EXISTS,
        verbose_name="Тип проверки"
    )
    
    # Пороговые значения
    threshold_min = models.FloatField(
        null=True, blank=True,
        verbose_name="Минимальный порог",
        help_text="Для threshold_min и threshold_range"
    )
    threshold_max = models.FloatField(
        null=True, blank=True,
        verbose_name="Максимальный порог",
        help_text="Для threshold_max и threshold_range"
    )
    
    # Минимальное изменение (для check_type='change')
    min_change = models.FloatField(
        null=True, blank=True,
        verbose_name="Минимальная дельта изменения",
        help_text="Для типа 'Изменение': разница между max и min за период. "
                  "Например 0.0001 для GPS координат."
    )
    
    # Описание для человека
    description = models.CharField(
        max_length=500,
        blank=True, default='',
        verbose_name="Описание проверки",
        help_text="Что проверяем и зачем. Например: 'GPS координаты должны меняться при работе'"
    )
    
    # Приоритет создаваемой задачи при провале проверки
    PRIORITY_CRITICAL = 'critical'
    PRIORITY_HIGH = 'high'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_LOW = 'low'
    PRIORITY_CHOICES = [
        (PRIORITY_CRITICAL, 'Критический'),
        (PRIORITY_HIGH, 'Высокий'),
        (PRIORITY_MEDIUM, 'Средний'),
        (PRIORITY_LOW, 'Низкий'),
    ]
    task_priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MEDIUM,
        verbose_name="Приоритет задачи",
        help_text="Приоритет задачи, которая будет создана при провале проверки"
    )
    
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Конфигурация тега мониторинга"
        verbose_name_plural = "Конфигурации тегов мониторинга"
        ordering = ['tag_name']
        # unique_together убран, т.к. ManyToMany не поддерживает.
        # Уникальность теперь по tag_name + clickhouse_table
        unique_together = ['tag_name', 'clickhouse_table']

    def __str__(self):
        return f"{self.tag_name} ({self.get_check_type_display()})"
    
    def clean(self):
        """Валидация: проверяем что пороги заполнены для соответствующих типов проверки."""
        from django.core.exceptions import ValidationError
        errors = {}
        
        if self.check_type == self.CHECK_THRESHOLD_MIN and self.threshold_min is None:
            errors['threshold_min'] = 'Укажите минимальный порог для этого типа проверки'
        
        if self.check_type == self.CHECK_THRESHOLD_MAX and self.threshold_max is None:
            errors['threshold_max'] = 'Укажите максимальный порог для этого типа проверки'
        
        if self.check_type == self.CHECK_THRESHOLD_RANGE:
            if self.threshold_min is None:
                errors['threshold_min'] = 'Укажите минимальный порог для диапазона'
            if self.threshold_max is None:
                errors['threshold_max'] = 'Укажите максимальный порог для диапазона'
        
        if self.check_type == self.CHECK_CHANGE and self.min_change is None:
            errors['min_change'] = 'Укажите минимальную дельту изменения'
        
        if errors:
            raise ValidationError(errors)
            # =====================================================================
# --- ГЕОЗОНЫ ДЛЯ МОНИТОРИНГА ---
# =====================================================================

class MonitoringGeozone(models.Model):
    """Геозона для фильтрации мониторинга телеметрии.
    
    Машины, находящиеся внутри геозоны, скрываются из мониторинга —
    они физически стоят на базе/ремзоне, но простой не зафиксирован.
    """
    name = models.CharField(max_length=255, verbose_name="Название", help_text="Например: База, Ремзона, Парковка")
    lat = models.FloatField(verbose_name="Широта центра", help_text="Например: 46.958700")
    lon = models.FloatField(verbose_name="Долгота центра", help_text="Например: 142.738300")
    radius_m = models.PositiveIntegerField(verbose_name="Радиус (метры)", default=500)
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    comment = models.TextField(blank=True, default='', verbose_name="Комментарий")

    class Meta:
        verbose_name = "Геозона мониторинга"
        verbose_name_plural = "Геозоны мониторинга"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (r={self.radius_m}м)"