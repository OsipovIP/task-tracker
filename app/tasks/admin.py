# tasks/admin.py

from django.contrib import admin, messages
from .models import (
    Task, TaskComment, TaskPhoto, OesObject, OesModel, OesCategory,
    FaultCategory, TaskCompletionReport, ManualAsset, IdleRecord, ModelTagConfig
)
from .utils import import_oes_objects_data
from .models import (
    Task, TaskComment, TaskPhoto, OesObject, OesModel, OesCategory,
    FaultCategory, TaskCompletionReport, ManualAsset, IdleRecord, ModelTagConfig,
    MonitoringGeozone  # добавить
)


# =====================================================================
# --- ДЕЙСТВИЯ (ACTIONS) ---
# =====================================================================

def update_oes_objects(modeladmin, request, queryset):
    """Admin action, которая запускает импорт"""
    success, message = import_oes_objects_data()
    if success:
        modeladmin.message_user(request, message, messages.SUCCESS)
    else:
        modeladmin.message_user(request, message, messages.ERROR)
update_oes_objects.short_description = "Обновить справочник Объектов OES из API"


def exclude_from_monitoring(modeladmin, request, queryset):
    """Исключить выбранные объекты из мониторинга."""
    count = queryset.update(exclude_from_monitoring=True)
    modeladmin.message_user(request, f'{count} объектов исключено из мониторинга.', messages.SUCCESS)
exclude_from_monitoring.short_description = "Исключить из мониторинга"


def include_in_monitoring(modeladmin, request, queryset):
    """Вернуть выбранные объекты в мониторинг."""
    count = queryset.update(exclude_from_monitoring=False, exclude_reason='')
    modeladmin.message_user(request, f'{count} объектов возвращено в мониторинг.', messages.SUCCESS)
include_in_monitoring.short_description = "Вернуть в мониторинг"


# =====================================================================
# --- OES МОДЕЛИ ---
# =====================================================================

@admin.register(OesObject)
class OesObjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_id', 'model', 'exclude_from_monitoring', 'exclude_reason')
    search_fields = ('name', 'source_id', 'mdm_object_uuid')
    list_filter = ('model__category', 'model', 'exclude_from_monitoring')
    list_editable = ('exclude_from_monitoring', 'exclude_reason')
    actions = [update_oes_objects, exclude_from_monitoring, include_in_monitoring]


@admin.register(OesModel)
class OesModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'category')
    search_fields = ('name', 'category__name')
    list_filter = ('category',)


@admin.register(OesCategory)
class OesCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_id')
    search_fields = ('name',)


# =====================================================================
# --- ЗАДАЧИ ---
# =====================================================================

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'itil_number', 'status', 'priority', 'reporter', 'assigned_to', 'created_at')
    list_filter = ('status', 'priority', 'created_at')
    search_fields = ('title', 'description', 'reporter__username', 'assigned_to__username', 'itil_number')
    raw_id_fields = ('oes_object',)
    autocomplete_fields = ('oes_object', 'manual_asset')
    readonly_fields = ('external_source', 'external_id', 'external_data', 'created_at', 'updated_at')

    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'description', 'status', 'priority', 'itil_number')
        }),
        ('Назначение', {
            'fields': ('reporter', 'assigned_to', 'assigned_group')
        }),
        ('Связь с оборудованием', {
            'fields': ('oes_object', 'manual_asset'),
            'classes': ('collapse',),
            'description': 'Выберите либо объект OES, либо ручной актив'
        }),
        ('Внешняя интеграция (ОТКЛЮЧЕНО)', {
            'fields': ('external_source', 'external_id', 'external_data'),
            'classes': ('collapse',),
            'description': 'ITIL функционал отключен. Данные сохранены для совместимости.'
        }),
        ('Даты и сроки', {
            'fields': ('due_date', 'acknowledged_at', 'created_at', 'updated_at')
        })
    )


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ('task', 'author', 'created_at')
    list_filter = ('created_at', 'author')


@admin.register(TaskPhoto)
class TaskPhotoAdmin(admin.ModelAdmin):
    list_display = ('task', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at', 'uploaded_by')


# =====================================================================
# --- ОТЧЁТНОСТЬ ---
# =====================================================================

@admin.register(FaultCategory)
class FaultCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    ordering = ('sort_order', 'name')


@admin.register(TaskCompletionReport)
class TaskCompletionReportAdmin(admin.ModelAdmin):
    list_display = ('task', 'completed_by', 'fault_category', 'created_at')
    list_filter = ('fault_category', 'created_at', 'completed_by')
    search_fields = ('task__title', 'work_performed', 'root_cause')
    readonly_fields = ('task', 'completed_by', 'created_at')

    fieldsets = (
        ('Основная информация', {
            'fields': ('task', 'completed_by', 'fault_category', 'time_spent')
        }),
        ('Отчет', {
            'fields': ('work_performed', 'root_cause', 'preventive_measures')
        }),
        ('Служебная информация', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )


# =====================================================================
# --- АКТИВЫ ---
# =====================================================================

@admin.register(ManualAsset)
class ManualAssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'asset_type', 'model', 'is_active', 'created_at')
    list_filter = ('asset_type', 'is_active', 'created_at')
    search_fields = ('name', 'asset_type', 'model', 'description')
    ordering = ('name',)
    list_editable = ('is_active',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'asset_type', 'model', 'description')
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
        ('Служебная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


# =====================================================================
# --- МОНИТОРИНГ ТЕЛЕМЕТРИИ ---
# =====================================================================

@admin.register(IdleRecord)
class IdleRecordAdmin(admin.ModelAdmin):
    list_display = ('external_id', 'oes_object', 'begin_dt', 'end_dt', 'duration', 'category_name', 'idle_type_name', 'shift_type', 'fetched_at')
    list_filter = ('shift_type', 'category_name', 'is_manual', 'fetched_at')
    search_fields = ('oes_object__name', 'category_name', 'comment')
    readonly_fields = ('external_id', 'raw_data', 'fetched_at')
    date_hierarchy = 'begin_dt'

    fieldsets = (
        ('Основное', {
            'fields': ('external_id', 'oes_object', 'object_uuid', 'object_id_external')
        }),
        ('Время', {
            'fields': ('begin_dt', 'end_dt', 'duration', 'duration_from_shift', 'shift_type')
        }),
        ('Классификация', {
            'fields': ('idle_type_id', 'idle_type_name', 'category_id', 'category_name')
        }),
        ('Детали', {
            'fields': ('comment', 'selected', 'is_manual', 'is_engine_on', 'is_allowed_zone')
        }),
        ('Геолокация', {
            'fields': ('lat', 'lon', 'geozones'),
            'classes': ('collapse',)
        }),
        ('Служебное', {
            'fields': ('updated_by', 'enterprise_id', 'raw_data', 'fetched_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ModelTagConfig)
class ModelTagConfigAdmin(admin.ModelAdmin):
    list_display = (
        'get_models_display', 'clickhouse_table', 'tag_name',
        'check_type', 'threshold_min', 'threshold_max',
        'min_change', 'task_priority', 'is_active'
    )
    list_filter = ('clickhouse_table', 'check_type', 'is_active', 'task_priority', 'oes_models')
    search_fields = ('tag_name', 'description', 'oes_model__name')
    list_editable = ('is_active', 'check_type', 'threshold_min', 'threshold_max', 'min_change', 'task_priority')

    fieldsets = (
        ('Привязка к моделям', {
            'fields': ('oes_models', 'clickhouse_table')
        }),
        ('Тег и проверка', {
            'fields': ('tag_name', 'check_type', 'description')
        }),
        ('Параметры проверки', {
            'fields': ('threshold_min', 'threshold_max', 'min_change'),
            'description': (
                'Заполняйте в зависимости от типа проверки:<br>'
                '• <b>Наличие данных</b> — параметры не нужны<br>'
                '• <b>Мин. порог</b> — заполните "Минимальный порог"<br>'
                '• <b>Макс. порог</b> — заполните "Максимальный порог"<br>'
                '• <b>Диапазон</b> — заполните оба порога<br>'
                '• <b>Изменение</b> — заполните "Минимальная дельта"'
            )
        }),
        ('Задача при провале', {
            'fields': ('task_priority',)
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ('tag_name',)
        return ()

    def get_models_display(self, obj):
        return ", ".join(m.name for m in obj.oes_models.all()[:3])
    get_models_display.short_description = "Модели"
    
@admin.register(MonitoringGeozone)
class MonitoringGeozoneAdmin(admin.ModelAdmin):
    list_display = ['name', 'lat', 'lon', 'radius_m', 'is_active']
    list_editable = ['is_active', 'radius_m']
    list_filter = ['is_active']