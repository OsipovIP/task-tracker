# tasks/admin.py (ОКОНЧАТЕЛЬНАЯ ВЕРСИЯ БЕЗ ДУБЛИРОВАНИЯ)

from django.contrib import admin, messages
from .models import Task, TaskComment, TaskPhoto, OesObject, OesModel, OesCategory, FaultCategory, TaskCompletionReport, ManualAsset
from .utils import import_oes_objects_data 

# Создаем Admin Action для запуска импорта
def update_oes_objects(modeladmin, request, queryset):
    """Admin action, которая запускает импорт"""
    success, message = import_oes_objects_data()
    
    if success:
        modeladmin.message_user(request, message, messages.SUCCESS)
    else:
        modeladmin.message_user(request, message, messages.ERROR)

update_oes_objects.short_description = "Обновить справочник Объектов OES из API"

# РЕГИСТРАЦИЯ OesObject - ТОЛЬКО ОДИН РАЗ!
@admin.register(OesObject)
class OesObjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_id', 'model')
    search_fields = ('name', 'source_id')
    list_filter = ('model__category', 'model')
    
    # Добавляем наше действие
    actions = [update_oes_objects] 


# РЕГИСТРАЦИЯ Task
@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    # ITIL ОТКЛЮЧЕНО - убрано external_source из отображения, добавлено itil_number
    list_display = ('id', 'title', 'itil_number', 'status', 'priority', 'reporter', 'assigned_to', 'created_at')
    list_filter = ('status', 'priority', 'created_at')  # убрано external_source
    search_fields = ('title', 'description', 'reporter__username', 'assigned_to__username', 'itil_number')  # добавлено itil_number
    raw_id_fields = ('oes_object',)  # Используем raw_id вместо select
    autocomplete_fields = ('oes_object', 'manual_asset')  # Включаем автокомплит
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
        # ITIL ОТКЛЮЧЕНО - секция скрыта, но поля сохранены в БД
        ('Внешняя интеграция (ОТКЛЮЧЕНО)', {
            'fields': ('external_source', 'external_id', 'external_data'),
            'classes': ('collapse',),
            'description': 'ITIL функционал отключен. Данные сохранены для совместимости.'
        }),
        ('Даты и сроки', {
            'fields': ('due_date', 'acknowledged_at', 'created_at', 'updated_at')
        })
    )

# РЕГИСТРАЦИЯ OesModel для автокомплита
@admin.register(OesModel)
class OesModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'category')
    search_fields = ('name', 'category__name')
    list_filter = ('category',)

# РЕГИСТРАЦИЯ OesCategory для автокомплита
@admin.register(OesCategory)
class OesCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_id')
    search_fields = ('name',)

# РЕГИСТРАЦИЯ TaskComment
@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ('task', 'author', 'created_at')
    list_filter = ('created_at', 'author')

# РЕГИСТРАЦИЯ TaskPhoto
@admin.register(TaskPhoto)
class TaskPhotoAdmin(admin.ModelAdmin):
    list_display = ('task', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at', 'uploaded_by')

# РЕГИСТРАЦИЯ FaultCategory
@admin.register(FaultCategory)
class FaultCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    ordering = ('sort_order', 'name')

# РЕГИСТРАЦИЯ TaskCompletionReport
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

# РЕГИСТРАЦИЯ ManualAsset
@admin.register(ManualAsset)
class ManualAssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'asset_type', 'model', 'is_active', 'created_at')
    list_filter = ('asset_type', 'is_active', 'created_at')
    search_fields = ('name', 'asset_type', 'model', 'description')
    ordering = ('name',)
    
    # Включаем автокомплит для использования в Task
    list_editable = ('is_active',)  # Можно быстро менять статус из списка
    
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
    
    readonly_fields = ('created_at', 'updated_at')


from .models import IdleRecord

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
    # --- Добавить в конец admin.py ---

from .models import ModelTagConfig

@admin.register(ModelTagConfig)
class ModelTagConfigAdmin(admin.ModelAdmin):
    list_display = (
        'oes_model', 'clickhouse_table', 'tag_name', 
        'check_type', 'threshold_min', 'threshold_max', 
        'min_change', 'task_priority', 'is_active'
    )
    list_filter = ('clickhouse_table', 'check_type', 'is_active', 'task_priority', 'oes_model')
    search_fields = ('tag_name', 'description', 'oes_model__name')
    list_editable = ('is_active', 'check_type', 'threshold_min', 'threshold_max', 'min_change', 'task_priority')
    
    fieldsets = (
        ('Привязка к модели', {
            'fields': ('oes_model', 'clickhouse_table')
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
        """При редактировании нельзя менять модель и тег (это ключ unique_together)."""
        if obj:
            return ('oes_model', 'tag_name')
        return ()