from django import forms
from .models import Task, TaskPhoto, TaskComment, OesObject, OesModel, FaultCategory, TaskCompletionReport, ManualAsset, RadioModel, RadioType, RadioAssignment, RadioRepair
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()

# --- Форма для создания задачи с автокомплитом (как в админке) ---
class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'assigned_to', 'assigned_group', 'status', 'priority', 'due_date', 'itil_number']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите заголовок задачи...'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Опишите задачу...'
            }),
            'assigned_to': forms.Select(attrs={
                'class': 'form-select'
            }),
            'assigned_group': forms.Select(attrs={
                'class': 'form-select'
            }),
            'status': forms.Select(attrs={
                'class': 'form-select'
            }),
            'priority': forms.Select(attrs={
                'class': 'form-select'
            }),
            'due_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'itil_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: INC0012345'
            })
        }
        labels = {
            'title': 'Заголовок задачи',
            'description': 'Описание',
            'assigned_to': 'Исполнитель',
            'assigned_group': 'Группа исполнителей',
            'status': 'Статус',
            'priority': 'Приоритет',
            'due_date': 'Срок выполнения',
            'itil_number': 'Номер ITIL'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Устанавливаем начальные значения
        self.fields['status'].initial = Task.STATUS_TODO
        self.fields['priority'].initial = Task.PRIORITY_MEDIUM
        
        # Делаем некоторые поля необязательными
        self.fields['assigned_group'].required = False
        self.fields['due_date'].required = False
        self.fields['itil_number'].required = False

# Форма для изменения статуса задачи
class TaskStatusForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['status']
        widgets = {
            'status': forms.Select(attrs={
                'class': 'form-select'
            })
        }

# Форма для загрузки фото
class TaskPhotoForm(forms.ModelForm):
    class Meta:
        model = TaskPhoto
        fields = ['image']
        widgets = {
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            })
        }

# Форма для комментариев
class TaskCommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Введите комментарий...'
            })
        }

# Форма для редактирования задач менеджерами
class TaskEditForm(forms.ModelForm):
    # Добавляем поле для поиска OES объекта (как в форме создания)
    oes_object_search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Начните вводить для поиска актива...',
            'autocomplete': 'off'
        }),
        label='Поиск актива'
    )
    
    class Meta:
        model = Task
        fields = ['title', 'description', 'assigned_to', 'assigned_group', 'oes_object', 'status', 'priority', 'due_date', 'itil_number']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4
            }),
            'assigned_to': forms.Select(attrs={
                'class': 'form-select'
            }),
            'assigned_group': forms.Select(attrs={
                'class': 'form-select'
            }),
            'oes_object': forms.HiddenInput(),  # Скрытое поле для oes_object
            'status': forms.Select(attrs={
                'class': 'form-select'
            }),
            'priority': forms.Select(attrs={
                'class': 'form-select'
            }),
            'due_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'itil_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: INC0012345'
            })
        }
        labels = {
            'title': 'Заголовок задачи',
            'description': 'Описание',
            'assigned_to': 'Исполнитель',
            'assigned_group': 'Группа исполнителей',
            'status': 'Статус',
            'priority': 'Приоритет',
            'due_date': 'Срок выполнения',
            'itil_number': 'Номер ITIL'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Заполняем списки пользователей и групп
        self.fields['assigned_to'].queryset = User.objects.all().order_by('username')
        self.fields['assigned_to'].empty_label = "Выберите исполнителя"
        
        self.fields['assigned_group'].queryset = Group.objects.all().order_by('name')
        self.fields['assigned_group'].empty_label = "Выберите группу"
        
        # Делаем поля необязательными
        self.fields['itil_number'].required = False
        
        # Устанавливаем начальное значение для поиска актива
        if self.instance and self.instance.oes_object:
            self.fields['oes_object_search'].initial = str(self.instance.oes_object)

# Форма для отчета о закрытии задачи
class TaskCompletionReportForm(forms.ModelForm):
    # Дополнительное поле для выбора исполнителей (не входит в модель отчета)
    additional_assignees = forms.ModelMultipleChoiceField(
        queryset=User.objects.all().order_by('username'),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-select',
            'size': '4'
        }),
        label='Дополнительные исполнители (до 3)',
        help_text='Удерживайте Ctrl (Cmd на Mac) для выбора нескольких'
    )
    
    class Meta:
        model = TaskCompletionReport
        fields = ['fault_category', 'work_performed', 'root_cause', 'preventive_measures', 'time_spent']
        widgets = {
            'fault_category': forms.Select(attrs={
                'class': 'form-select'
            }),
            'work_performed': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Опишите, что именно было сделано...'
            }),
            'root_cause': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Укажите причину возникновения проблемы...'
            }),
            'preventive_measures': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Опишите меры для предотвращения повторения...'
            }),
            'time_spent': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time',
                'placeholder': 'ЧЧ:ММ'
            })
        }
        labels = {
            'fault_category': 'Категория неисправности',
            'work_performed': 'Выполненная работа',
            'root_cause': 'Корневая причина',
            'preventive_measures': 'Предупредительные меры',
            'time_spent': 'Затраченное время'
        }

    def __init__(self, *args, **kwargs):
        # Извлекаем task из kwargs, если передан
        task = kwargs.pop('task', None)
        super().__init__(*args, **kwargs)
        
        # Заполняем список категорий неисправностей
        self.fields['fault_category'].queryset = FaultCategory.objects.filter(is_active=True).order_by('sort_order', 'name')
        self.fields['fault_category'].empty_label = "Выберите категорию неисправности"
        
        # Если task передан, устанавливаем начальные значения для additional_assignees
        if task and task.pk:
            self.fields['additional_assignees'].initial = task.additional_assignees.all()
        
        # Делаем некоторые поля необязательными
        self.fields['root_cause'].required = False
        self.fields['preventive_measures'].required = False
        self.fields['time_spent'].required = False
    
    def clean_additional_assignees(self):
        additional = self.cleaned_data.get('additional_assignees')
        if additional and additional.count() > 3:
            raise forms.ValidationError('Можно выбрать не более 3 дополнительных исполнителей.')
        return additional


# Форма для создания и закрытия задачи
class CreateAndCloseTaskForm(forms.ModelForm):
    """Форма для быстрого создания задачи с автоматическим закрытием."""
    # Поле для поиска актива (OES или ручной)
    asset_search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control asset-search-input',
            'placeholder': 'Начните вводить для поиска актива...',
            'autocomplete': 'off',
            'id': 'asset_search_field'
        }),
        label='Актив'
    )
    
    fault_category = forms.ModelChoiceField(
        queryset=FaultCategory.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Категория неисправности'
    )
    
    work_performed = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Опишите выполненную работу...'}),
        label='Выполненная работа'
    )
    
    class Meta:
        model = Task
        fields = ['title', 'description', 'itil_number']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'itil_number': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'title': 'Заголовок задачи',
            'description': 'Описание',
            'itil_number': 'Номер ITIL',
        }


# Формы для учета раций
class RadioModelForm(forms.ModelForm):
    """Форма для добавления модели рации в справочник."""
    class Meta:
        model = RadioModel
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'Название модели',
            'description': 'Описание',
            'is_active': 'Активна',
        }


class RadioTypeForm(forms.ModelForm):
    """Форма для добавления рации в справочник."""
    class Meta:
        model = RadioType
        fields = ['model', 'sn', 'ccid', 'sim', 'description', 'is_active']
        widgets = {
            'model': forms.Select(attrs={'class': 'form-select'}),
            'sn': forms.TextInput(attrs={'class': 'form-control'}),
            'ccid': forms.TextInput(attrs={'class': 'form-control'}),
            'sim': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'model': 'Модель',
            'sn': 'Серийный номер',
            'ccid': 'CCID',
            'sim': 'ID',
            'description': 'Описание',
            'is_active': 'Статус (активна)',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['model'].queryset = RadioModel.objects.filter(is_active=True)


class RadioAssignmentForm(forms.ModelForm):
    """Форма для выдачи рации."""
    assignee_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Введите имя получателя'}),
        label='Выдать кому'
    )
    
    class Meta:
        model = RadioAssignment
        fields = ['device', 'department', 'notes', 'pdf_file']
        widgets = {
            'device': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'pdf_file': forms.FileInput(attrs={'class': 'form-control', 'accept': 'application/pdf'}),
        }
        labels = {
            'pdf_file': 'PDF файл (прикрепить акт)',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Если форма для редактирования (instance передан), делаем device read-only
        if self.instance and self.instance.pk:
            self.fields['device'].disabled = True
            self.fields['device'].required = False
            # Сбрасываем фильтрацию для read-only поля
            self.fields['device'].queryset = RadioType.objects.all()
        else:
            # Фильтруем только активные рации для новой выдачи
            self.fields['device'].queryset = RadioType.objects.filter(is_active=True)
            
            # Исключаем рации, которые уже выданы (не возвращены)
            issued_radio_ids = RadioAssignment.objects.filter(returned_at__isnull=True).values_list('device_id', flat=True)
            self.fields['device'].queryset = self.fields['device'].queryset.exclude(id__in=issued_radio_ids)

    def clean_device(self):
        """Серверная проверка: нельзя выдать рацию, если есть активная выдача."""
        device = self.cleaned_data.get('device')
        if device is None:
            return device
        
        # Если редактируем существующую запись, проверка не нужна
        if self.instance and self.instance.pk:
            return device
        
        # Только для новой выдачи проверяем, что рация не выдана
        exists_open = RadioAssignment.objects.filter(device=device, returned_at__isnull=True).exists()
        if exists_open:
            raise forms.ValidationError('Эта рация уже выдана и еще не возвращена.')
        return device


class RadioRepairForm(forms.ModelForm):
    """Форма для учета ремонта рации."""
    class Meta:
        model = RadioRepair
        fields = ['device', 'repair_date', 'description']
        widgets = {
            'device': forms.Select(attrs={'class': 'form-select'}),
            'repair_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Фильтруем только активные рации
        self.fields['device'].queryset = RadioType.objects.filter(is_active=True)