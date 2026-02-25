import requests
import json
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from tasks import models as task_models

class Command(BaseCommand):
    help = 'Импортирует и обновляет иерархию OES-объектов с удаленного API, используя пакетные операции для скорости.'
    
    API_URL = "https://meta.oeswork.io/api/diagnostics/objects"
    # Размер пакета для bulk_create. Можно настроить в зависимости от памяти.
    BATCH_SIZE = 1000 

    def handle(self, *args, **options):
        self.stdout.write(f"Подключение к API: {self.API_URL}")
        
        try:
            response = requests.get(self.API_URL, timeout=60) 
            response.raise_for_status()
            data = response.json()
            
        except requests.exceptions.RequestException as e:
            raise CommandError(f'Ошибка при получении данных с API: {e}')
        except json.JSONDecodeError:
            raise CommandError('Ошибка декодирования JSON. Проверьте формат ответа API.')

        if not isinstance(data, list):
            raise CommandError('Ожидался список категорий JSON.')

        # Общие счетчики
        stats = {
            'categories': 0, 'models': 0, 'objects': 0, 'devices': 0,
            'models_created': 0, 'models_updated': 0,
            'objects_created': 0, 'objects_updated': 0,
            'devices_created': 0, 'devices_updated': 0,
        }

        with transaction.atomic():
            
            # --- 1. Обработка Категорий (OesCategory) ---
            # Категорий обычно немного, используем get_or_create для простоты
            category_map = {} # source_id -> OesCategory object
            for category_data in data:
                category_obj, created = task_models.OesCategory.objects.get_or_create(
                    source_id=category_data['id'],
                    defaults={'name': category_data['name']}
                )
                category_map[category_data['id']] = category_obj
                stats['categories'] += 1
            
            self.stdout.write(self.style.NOTICE(f"Категории обработаны ({stats['categories']}). Переход к пакетной обработке..."))

            # --- 2. Сбор всех данных для пакетной обработки ---
            
            # Списки для сбора всех данных API
            all_model_data = []
            all_object_data = []
            all_device_data = []
            
            # Временные словари для хранения объектов Моделей и Объектов, 
            # созданных на этом шаге, чтобы их можно было связать на следующем
            model_map = {} # source_id -> OesModel object (временная)
            object_map = {} # mdm_object_uuid -> OesObject object (временная)

            for category_data in data:
                category_obj = category_map.get(category_data['id'])
                if not category_obj: continue

                # Сбор Моделей
                for model_data in category_data.get('models', []):
                    all_model_data.append({
                        'source_id': model_data['id'],
                        'category_obj': category_obj,
                        'name': model_data['name'],
                        'objects': model_data.get('objects', []) # Сохраняем вложенные данные
                    })
                
                # Сбор Объектов и Устройств (нужно для связи OesObject с OesObjectDevice)
                # Эта часть будет обработана в следующем шаге, но данные уже собраны в all_model_data

            # --- 3. Пакетная обработка OesModel ---
            self._process_bulk(
                task_models.OesModel, 
                all_model_data, 
                'source_id', 
                'source_id', 
                lambda d: task_models.OesModel(
                    source_id=d['source_id'], 
                    category=d['category_obj'], 
                    name=d['name']
                ),
                lambda d: {'category': d['category_obj'], 'name': d['name']},
                stats, 'models', model_map,
                None # ИСПРАВЛЕНИЕ: Удалено d.pop('objects'), чтобы сохранить данные для Шага 4
            )
            self.stdout.write(self.style.SUCCESS(f"Модели обработаны: создано {stats['models_created']}, обновлено {stats['models_updated']}"))
            
            # --- 4. Пакетная обработка OesObject (зависит от OesModel) ---
            
            # Пересобираем все данные объектов из all_model_data, используя model_map
            all_object_data = []
            zero_uuid = "00000000-0000-0000-0000-000000000000"
            
            for model_id, model_obj in model_map.items():
                for item in all_model_data:
                    # Проверяем, что 'objects' существует и не пуст
                    objects_list = item.get('objects', [])
                    if item['source_id'] == model_id and objects_list: 
                        for object_data in objects_list:
                            mdm_uuid = object_data.get('mdm_object_uuid')
                            source_id = object_data.get('id')
                            
                            
                            # Для объектов с нулевым UUID используем source_id как уникальный идентификатор
                            # Для остальных - mdm_object_uuid
                            if not mdm_uuid or mdm_uuid.strip() == '' or mdm_uuid == zero_uuid:
                                # Используем source_id как lookup_key для объектов с нулевым или отсутствующим UUID
                                lookup_key = f"source_id_{source_id}"
                                use_source_id_as_primary = True
                            else:
                                lookup_key = mdm_uuid
                                use_source_id_as_primary = False
                            
                            all_object_data.append({
                                'mdm_object_uuid': mdm_uuid if mdm_uuid and mdm_uuid != zero_uuid else None,
                                'source_id': source_id,
                                'model_obj': model_obj,
                                'name': object_data['name'],
                                'devices': object_data.get('object_devices', []),
                                'lookup_key': lookup_key,
                                'use_source_id': use_source_id_as_primary
                            })
                        break # Нашли модель, переходим к следующей
            
            # Разделяем объекты на две группы: с нормальным UUID и с нулевым UUID
            normal_objects = [d for d in all_object_data if not d['use_source_id']]
            zero_uuid_objects = [d for d in all_object_data if d['use_source_id']]
            
            # Обрабатываем объекты с нормальным UUID
            if normal_objects:
                self._process_bulk(
                    task_models.OesObject,
                    normal_objects,
                    'mdm_object_uuid',
                    'mdm_object_uuid',
                    lambda d: task_models.OesObject(
                        mdm_object_uuid=d['mdm_object_uuid'],
                        source_id=d['source_id'],
                        model=d['model_obj'],
                        name=d['name']
                    ),
                    lambda d: {'source_id': d['source_id'], 'model': d['model_obj'], 'name': d['name']},
                    stats, 'objects', object_map,
                    None
                )
            
            # Обрабатываем объекты с нулевым UUID отдельно, используя source_id
            if zero_uuid_objects:
                self.stdout.write(self.style.WARNING(f"Найдено {len(zero_uuid_objects)} объектов с нулевым UUID, обрабатываем по source_id"))
                self._process_bulk(
                    task_models.OesObject,
                    zero_uuid_objects,
                    'source_id',  # Используем source_id для поиска
                    'source_id',  # И в API используем source_id
                    lambda d: task_models.OesObject(
                        mdm_object_uuid=None,  # Устанавливаем None для нулевого UUID
                        source_id=d['source_id'],
                        model=d['model_obj'],
                        name=d['name']
                    ),
                    lambda d: {'mdm_object_uuid': None, 'model': d['model_obj'], 'name': d['name']},
                    stats, 'objects', object_map,
                    None
                )
            self.stdout.write(self.style.SUCCESS(f"Объекты обработаны: создано {stats['objects_created']}, обновлено {stats['objects_updated']}"))

        # --- 5. Пакетная обработка OesObjectDevice (зависит от OesObject) ---
        # Обрабатываем устройства в ОТДЕЛЬНОЙ транзакции, чтобы ошибка не откатила объекты
        # Пропускаем обработку устройств, если таблица не готова
        with transaction.atomic():
            try:
                # Проверяем, есть ли нужное поле в таблице, пытаясь выполнить запрос
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'tasks_oesobjectdevice' 
                        AND column_name IN ('source_object_id', 'source_id')
                    """)
                    existing_columns = [row[0] for row in cursor.fetchall()]
                
                if not existing_columns:
                    # Если нет нужных полей, пропускаем устройства
                    self.stdout.write(self.style.WARNING("Таблица устройств не содержит нужных полей. Обработка устройств пропущена."))
                    stats['devices_created'] = 0
                    stats['devices_updated'] = 0
                else:
                    # Определяем, какое поле использовать для поиска
                    lookup_field = 'source_object_id' if 'source_object_id' in existing_columns else 'source_id'
                    
                    # Пересобираем все данные устройств из all_object_data, используя object_map
                    all_device_data = []
                    # Создаем обратный маппинг: source_id -> object_obj для объектов с нулевым UUID
                    source_id_to_object = {}
                    for obj_key, object_obj in object_map.items():
                        # Если ключ начинается с "source_id_", это объект с нулевым UUID
                        if isinstance(obj_key, str) and obj_key.startswith('source_id_'):
                            source_id = int(obj_key.replace('source_id_', ''))
                            source_id_to_object[source_id] = object_obj
                    
                    # Обрабатываем устройства для объектов с нормальным UUID
                    for mdm_uuid, object_obj in object_map.items():
                        if isinstance(mdm_uuid, str) and mdm_uuid.startswith('source_id_'):
                            continue  # Пропускаем объекты с нулевым UUID здесь
                        for item in all_object_data:
                            devices_list = item.get('devices', [])
                            if item.get('mdm_object_uuid') == mdm_uuid and devices_list:
                                for device_data in devices_list:
                                    # Используем доступное поле как идентификатор
                                    if lookup_field == 'source_object_id':
                                        lookup_value = device_data.get('source_object_id')
                                        if not lookup_value:
                                            continue
                                    else:
                                        lookup_value = device_data.get('id')
                                        if not lookup_value:
                                            continue
                                    
                                    all_device_data.append({
                                        'source_id': device_data.get('id'),
                                        'source_object_id': device_data.get('source_object_id', f"device_{device_data.get('id', 'unknown')}"),
                                        'lookup_value': lookup_value,
                                        'oes_object_obj': object_obj,
                                    })
                                break
                    
                    # Обрабатываем устройства для объектов с нулевым UUID (используем source_id для связи)
                    for source_id, object_obj in source_id_to_object.items():
                        for item in all_object_data:
                            # Ищем объект по source_id
                            if item.get('source_id') == source_id:
                                devices_list = item.get('devices', [])
                                if devices_list:
                                    for device_data in devices_list:
                                        if lookup_field == 'source_object_id':
                                            lookup_value = device_data.get('source_object_id')
                                            if not lookup_value:
                                                continue
                                        else:
                                            lookup_value = device_data.get('id')
                                            if not lookup_value:
                                                continue
                                        
                                        all_device_data.append({
                                            'source_id': device_data.get('id'),
                                            'source_object_id': device_data.get('source_object_id', f"device_{device_data.get('id', 'unknown')}"),
                                            'lookup_value': lookup_value,
                                            'oes_object_obj': object_obj,
                                        })
                                break
                    
                    # Обрабатываем устройства только если они есть
                    if all_device_data:
                        try:
                            self._process_bulk(
                                task_models.OesObjectDevice,
                                all_device_data,
                                lookup_field,  # Используем определенное поле
                                'lookup_value',  # В данных используем lookup_value
                                lambda d: task_models.OesObjectDevice(
                                    source_id=d.get('source_id'),
                                    source_object_id=d.get('source_object_id', f"device_{d.get('source_id', 'unknown')}"),
                                    oes_object=d['oes_object_obj']
                                ),
                                lambda d: {'source_id': d.get('source_id'), 'source_object_id': d.get('source_object_id'), 'oes_object': d['oes_object_obj']},
                                stats, 'devices', None,
                                None
                            )
                            self.stdout.write(self.style.SUCCESS(f"Устройства обработаны: создано {stats['devices_created']}, обновлено {stats['devices_updated']}"))
                        except Exception as device_error:
                            # Если ошибка при обработке устройств, логируем и продолжаем
                            self.stdout.write(self.style.ERROR(
                                f"Ошибка при обработке устройств: {str(device_error)}"
                            ))
                            stats['devices_created'] = 0
                            stats['devices_updated'] = 0
                    else:
                        self.stdout.write(self.style.WARNING("Устройства не найдены в данных API"))
            except Exception as e:
                # Если таблица не существует или произошла ошибка, просто пропускаем устройства
                self.stdout.write(self.style.WARNING(f"Обработка устройств пропущена: {str(e)}"))
                stats['devices_created'] = 0
                stats['devices_updated'] = 0
                # Важно: не пропускаем исключение дальше, чтобы не откатить транзакцию устройств


        self.stdout.write(self.style.SUCCESS(
            f'Импорт успешно завершен! '
            f'Категорий: {stats["categories"]}, Моделей: {stats["models_created"] + stats["models_updated"]}, '
            f'Объектов: {stats["objects_created"] + stats["objects_updated"]}, Устройств: {stats["devices_created"] + stats["devices_updated"]}'
        ))

    def _process_bulk(self, model_class, data_list, lookup_field, api_lookup_field, create_instance_func, update_defaults_func, stats, model_name, instance_map=None, after_pop_func=None):
        """Вспомогательная функция для пакетной обработки CREATE/UPDATE."""
        
        # 0. ИСПРАВЛЕНИЕ: Дедупликация входных данных, чтобы избежать UniqueViolation при bulk_create
        unique_data_map = {}
        for item_data in data_list:
            # Используем lookup_field в качестве ключа для дедупликации
            # Если в списке API есть дубликаты, берем последний, что обычно безопасно.
            unique_data_map[item_data[api_lookup_field]] = item_data
        
        # Заменяем data_list на дедуплицированный список
        data_list = list(unique_data_map.values())
        
        # 1. Сбор существующих ID из базы
        # Используем values_list, чтобы получить только поле lookup_field
        # Для source_id проверяем все объекты, независимо от mdm_object_uuid
        if lookup_field == 'source_id' and model_class == task_models.OesObject:
            # Для объектов с нулевым UUID проверяем существование по source_id независимо от mdm_object_uuid
            # Используем distinct() чтобы избежать дубликатов при наличии нескольких объектов с одним source_id
            existing_ids = set(model_class.objects.values_list(lookup_field, flat=True).distinct())
        else:
            existing_ids = set(model_class.objects.values_list(lookup_field, flat=True))
        
        to_create = []
        to_update = []
        
        # 2. Разделение на списки "создать" и "обновить"
        # Пересчитываем stats[model_name] на основе дедуплицированных данных
        stats[model_name] = 0
        for item_data in data_list:
            stats[model_name] += 1
            lookup_value = item_data[api_lookup_field]
            
            
            if lookup_value in existing_ids:
                # Обновление. 
                item_data['pk'] = lookup_value
                to_update.append(item_data)
            else:
                # Создание
                to_create.append(item_data)

        # --- Создание новых объектов ---
        new_instances = []
        for d in to_create:
            instance = create_instance_func(d)
            new_instances.append(instance)
        
        # Пакетное создание (bulk_create)
        # Используем ignore_conflicts=True для обработки дубликатов (race condition или другие причины)
        if new_instances:
            created_instances = model_class.objects.bulk_create(
                new_instances, 
                batch_size=self.BATCH_SIZE,
                ignore_conflicts=True
            )
            stats[f'{model_name}_created'] += len(created_instances)

        # --- Обновление существующих объектов ---
        update_fields = set()
        
        # Сначала получаем все объекты, которые нужно обновить, чтобы получить их PK
        update_keys = [d[lookup_field] for d in to_update]
        # in_bulk возвращает {lookup_value: instance}
        existing_instances = model_class.objects.filter(**{f'{lookup_field}__in': update_keys}).in_bulk(field_name=lookup_field)
        
        instances_to_save = []
        
        for d in to_update:
            instance = existing_instances.get(d[lookup_field])
            if instance:
                defaults = update_defaults_func(d)
                for field, value in defaults.items():
                    setattr(instance, field, value)
                    update_fields.add(field)
                instances_to_save.append(instance)
        
        # Пакетное обновление (bulk_update)
        if instances_to_save:
            # Преобразование set в list обязательно
            model_class.objects.bulk_update(instances_to_save, list(update_fields), batch_size=self.BATCH_SIZE)
            stats[f'{model_name}_updated'] += len(instances_to_save)

        # --- Создание карты экземпляров (для связывания зависимостей) ---
        if instance_map is not None:
            # Перечитываем все созданные и обновленные объекты, чтобы получить их полные экземпляры.
            all_keys = set(update_keys) | {d[lookup_field] for d in to_create}
            
            # lookup_param всегда должен быть lookup_field (mdm_object_uuid или source_id)
            lookup_param = lookup_field 

            # Запрашиваем полные инстансы из БД
            for instance in model_class.objects.filter(**{f'{lookup_param}__in': all_keys}):
                lookup_value = getattr(instance, lookup_param)
                # Для объектов с нулевым UUID используем source_id как ключ с префиксом
                if lookup_param == 'source_id' and model_class == task_models.OesObject:
                    instance_map[f'source_id_{lookup_value}'] = instance
                else:
                    instance_map[lookup_value] = instance
            
            # Применяем post-обработку (если есть), но избегаем pop для сохранения потока данных
            if after_pop_func:
                for d in data_list:
                    after_pop_func(d)
