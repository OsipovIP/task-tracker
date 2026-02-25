# tasks/utils.py 
import requests
from django.utils import timezone
from .models import OesObject
from django.db import transaction

# URL внешнего API
API_URL = "https://meta.oeswork.io/api/diagnostics/objects"

def import_oes_objects_data():
    """
    Загружает и синхронизирует объекты OES из внешнего API.
    Возвращает (success: bool, message: str)
    """
    try:
        response = requests.get(API_URL, timeout=30)
        response.raise_for_status() # Вызывает исключение при ошибке HTTP
        
        data = response.json()
        
        objects_to_update = []
        
        with transaction.atomic():
            for item in data:
                external_id = item.get('id')
                name = item.get('name') 
                
                if external_id and name:
                    # Используем get_or_create для обновления или создания
                    obj, created = OesObject.objects.get_or_create(
                        external_id=external_id,
                        defaults={
                            'name': name,
                            'data': item,
                        }
                    )
                    # Если объект уже существовал, обновляем его
                    if not created:
                        obj.name = name
                        obj.data = item
                        objects_to_update.append(obj)

            # Массовое обновление существующих объектов
            if objects_to_update:
                OesObject.objects.bulk_update(objects_to_update, ['name', 'data'])

        count = len(data)
        return True, f"Импорт успешно завершен. Обработано {count} объектов."
        
    except requests.exceptions.RequestException as e:
        return False, f"Ошибка при доступе к API: {e}"
    except Exception as e:
        return False, f"Непредвиденная ошибка: {e}"