"""
Management-команда для проверки телеметрии работающей техники.

Логика:
1. Берём все OesObject
2. Вычитаем те, что сейчас в простое (IdleRecord за текущую смену)
3. Для работающих машин берём ModelTagConfig по их OesModel
4. Запрашиваем ClickHouse пачками по таблицам (trucks / heavy_equipment)
5. Выводим результат

Использование:
    python manage.py check_telemetry           # Проверка всех работающих машин
    python manage.py check_telemetry --dry-run # Только показать, без создания задач
"""

import logging
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.utils import timezone
from tasks.models import OesObject, IdleRecord, ModelTagConfig
from tasks.clickhouse_client import ClickHouseClient

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Проверка телеметрии работающей техники через ClickHouse'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать результат, не создавать задачи'
        )
        parser.add_argument(
            '--hours',
            type=int,
            default=1,
            help='За сколько часов проверять (по умолчанию 1)'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        hours = options['hours']
        
        self.stdout.write(f"Проверка телеметрии за последние {hours} ч.")
        
        # 1. Проверяем подключение к ClickHouse
        ch = ClickHouseClient()
        if not ch.test_connection():
            self.stdout.write(self.style.ERROR("Нет подключения к ClickHouse!"))
            return
        self.stdout.write(self.style.SUCCESS("ClickHouse: подключение OK"))
        
        # 2. Получаем активные конфигурации тегов
        tag_configs = ModelTagConfig.objects.filter(
            is_active=True
        ).prefetch_related('oes_models')
        
        if not tag_configs:
            self.stdout.write(self.style.WARNING(
                "Нет активных конфигураций тегов. "
                "Добавьте их через Django Admin → Конфигурации тегов мониторинга."
            ))
            return
        
        # Группируем конфиги по (модель, таблица)
        # {(oes_model_id, ch_table): [tag_config, ...]}
        configs_by_model_table = defaultdict(list)
        models_with_configs = set()
        for tc in tag_configs:
            for oes_model in tc.oes_models.all():
                key = (oes_model.id, tc.clickhouse_table)
                if tc not in configs_by_model_table[key]:
                    configs_by_model_table[key].append(tc)
                models_with_configs.add(oes_model.id)
        
        self.stdout.write(
            f"Конфигураций тегов: {tag_configs.count()}, "
            f"моделей с мониторингом: {len(models_with_configs)}"
        )
        
        # 3. Получаем объекты с source_id, у которых модель имеет конфигурацию
        all_objects = OesObject.objects.filter(
            model_id__in=models_with_configs,
            source_id__isnull=False,
            exclude_from_monitoring=False
        ).select_related('model', 'model__category')
        
        self.stdout.write(f"Объектов с мониторингом: {all_objects.count()}")
        
        # 4. Получаем ID объектов в простое (текущие незавершённые)
        idle_object_ids = set(
            IdleRecord.objects.filter(
                end_dt__isnull=True,  # незавершённые простои
                oes_object__isnull=False
            ).values_list('oes_object__source_id', flat=True)
        )
        
        # 5. Фильтруем: только работающие машины
        working_objects = [
            obj for obj in all_objects 
            if obj.source_id not in idle_object_ids
        ]
        
        self.stdout.write(
            f"В простое: {len(idle_object_ids)}, "
            f"в работе: {len(working_objects)}"
        )
        
        if not working_objects:
            self.stdout.write(self.style.WARNING("Нет работающих машин для проверки."))
            return
        
        # 6. Группируем рабочие объекты по (модель, таблица)
        objects_by_model_table = defaultdict(list)
        for obj in working_objects:
            for key in configs_by_model_table:
                model_id, ch_table = key
                if obj.model_id == model_id:
                    objects_by_model_table[key].append(obj)
        
        # 7. Запрашиваем ClickHouse пачками
        all_results = {}  # {oes_object: {tag_name: {status, detail, values}}}
        
        for (model_id, ch_table), objects in objects_by_model_table.items():
            if not objects:
                continue
            
            tag_confs = configs_by_model_table[(model_id, ch_table)]
            object_uuids = [obj.mdm_object_uuid for obj in objects if obj.mdm_object_uuid]
            
            model_name = objects[0].model.name if objects[0].model else 'Unknown'
            self.stdout.write(
                f"\n  Проверка: {model_name} ({ch_table}), "
                f"объектов: {len(objects)}, тегов: {len(tag_confs)}"
            )
            
            # Один запрос на всю группу
            ch_results = ch.check_tags_batch(
                table=ch_table,
                object_uuids=object_uuids,
                tag_configs=tag_confs,
                hours=hours
            )
            
            # Маппим обратно на объекты
            obj_by_uuid = {obj.mdm_object_uuid: obj for obj in objects if obj.mdm_object_uuid}
            for uuid, tags_data in ch_results.items():
                obj = obj_by_uuid.get(uuid)
                if obj:
                    all_results[obj] = tags_data
        
        # 8. Выводим результаты
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write("РЕЗУЛЬТАТЫ ПРОВЕРКИ")
        self.stdout.write(f"{'='*80}")
        
        ok_count = 0
        fail_count = 0
        warn_count = 0
        
        for obj, tags_data in all_results.items():
            has_issues = any(
                d['status'] in ('fail', 'warn') 
                for d in tags_data.values()
            )
            
            if has_issues:
                self.stdout.write(f"\n  {obj.name} ({obj.model.name if obj.model else '?'}):")
                for tag_name, data in tags_data.items():
                    status = data['status']
                    detail = data['detail']
                    
                    if status == 'ok':
                        ok_count += 1
                        icon = '✅'
                    elif status == 'warn':
                        warn_count += 1
                        icon = '⚠️'
                    else:
                        fail_count += 1
                        icon = '❌'
                    
                    self.stdout.write(f"    {icon} {tag_name}: {detail}")
            else:
                ok_count += len(tags_data)
        
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(
            f"Итого: ✅ {ok_count} ok, ⚠️ {warn_count} warn, ❌ {fail_count} fail"
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n[DRY RUN] Задачи не создаются."))
