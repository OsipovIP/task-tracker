from django.urls import path
from . import views

urlpatterns = [
    # Список всех задач пользователя
    path('', views.task_list, name='task_list'),
    
    # Детали задачи
    path('<int:pk>/', views.task_detail, name='task_detail'),
    
    # МАРШРУТ: Захват задачи из пула
    path('<int:pk>/claim/', views.task_claim, name='task_claim'), 
    
    # Подтверждение получения задачи
    path('<int:pk>/confirm/', views.task_confirm_receipt, name='task_confirm_receipt'), 
    
    # НОВЫЙ МАРШРУТ ДЛЯ AJAX: Загрузка объектов OesObject по выбранной OesModel
    path('ajax/load-objects/', views.load_objects, name='ajax_load_objects'), 
    
    # МАРШРУТ: Создание новой задачи
    path('create/', views.task_create, name='task_create'),
    
    # МАРШРУТ: Создание и закрытие задачи
    path('create-and-close/', views.create_and_close_task, name='create_and_close_task'), 
    
    # НОВЫЕ МАРШРУТЫ: Дополнительные страницы
    path('pool/', views.task_pool, name='task_pool'),  # Наряд (задачи к выполнению)
    path('all/', views.all_tasks, name='all_tasks'),   # Все задачи с фильтром
    path('export-excel/', views.export_tasks_to_excel, name='export_tasks_to_excel'),  # Экспорт в Excel
    path('work-order/', views.work_order_management, name='work_order_management'),  # Формирование наряда
    path('checking/', views.tasks_for_checking, name='tasks_for_checking'),  # Задачи на проверке
    
    # URLs для учета раций
    path('radios/', views.radio_list, name='radio_list'),
    path('radios/add/', views.radio_add, name='radio_add'),
    path('radios/<int:pk>/edit/', views.radio_edit, name='radio_edit'),
    path('radios/models/', views.radio_models_list, name='radio_models_list'),
    path('radios/models/add/', views.radio_model_add, name='radio_model_add'),
    path('radios/models/<int:pk>/edit/', views.radio_model_edit, name='radio_model_edit'),
    path('radios/assign/', views.radio_assign, name='radio_assign'),
    path('radios/assignments/', views.radio_assignments_list, name='radio_assignments_list'),
    path('radios/assignments/<int:pk>/edit/', views.radio_assignment_edit, name='radio_assignment_edit'),
    path('radios/assignments/<int:pk>/act.xlsx', views.radio_assignment_act_excel, name='radio_assignment_act_excel'),
    path('radios/return/<int:pk>/', views.radio_return, name='radio_return'),
    path('radios/repair/', views.radio_repair, name='radio_repair'),
    path('radios/repairs/', views.radio_repairs_list, name='radio_repairs_list'),
    # Мониторинг телеметрии
    path('telemetry/', views.telemetry_monitor, name='telemetry_monitor'),
    path('telemetry/create-task/<int:object_id>/', views.create_telemetry_task, name='create_telemetry_task'),
    path('telemetry/create-tasks-bulk/', views.create_telemetry_tasks_bulk, name='create_telemetry_tasks_bulk'),
]
