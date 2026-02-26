"""
Management-команда для загрузки простоев техники из внешнего API.

Использование:
    python manage.py fetch_idles              # Автоопределение смены по текущему времени
    python manage.py fetch_idles --shift day  # Принудительно дневная смена
    python manage.py fetch_idles --shift night # Принудительно ночная смена
    python manage.py fetch_idles --date 2026-02-25  # Конкретная дата
    python manage.py fetch_idles --current    # Все незавершённые простои (для мониторинга)

Расписание cron (Asia/Sakhalin):
    50 7 * * *  - после ночной смены (19:45 вчера → 07:45 сегодня)
    50 19 * * * - после дневной смены (07:45 → 19:45 сегодня)
"""

import requests
import logging
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from tasks.models import IdleRecord, OesObject
from django.utils.timezone import make_aware
from datetime import datetime as dt
import pytz

SAKHALIN_TZ = pytz.timezone('Asia/Sakhalin')

logger = logging.getLogger(__name__)

# URL API простоев
API_URL = "https://idles.oeswork.io/api/idles"

# Фиксированные параметры запроса
FIXED_PARAMS = {
    "status": "notCompleted",
    "min_minutes": 10,
    "enterprise_uuids": [],
    "object_model_uuids": [],
    "object_type_uuids": [],
    "object_uuids": [],
    "idle_type_ids": [],
    "idle_category_ids": [163, 162, 9, 12, 11, 3, 13, 10, 15, 161],
    "is_manual": True,
    "sort_by": "end_dt",
    "sort_order": "asc",
    "per_page": 150,
}

# Время начала/конца смен
DAY_SHIFT_START_HOUR = 7
DAY_SHIFT_START_MIN = 45
NIGHT_SHIFT_START_HOUR = 19
NIGHT_SHIFT_START_MIN = 45


class Command(BaseCommand):
    help = 'Загрузка простоев техники из внешнего API (idles.oeswork.io)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--shift',
            type=str,
            choices=['day', 'night'],
            help='Тип смены: day (дневная 07:45-19:45) или night (ночная 19:45-07:45). '
                 'По умолчанию определяется автоматически.'
        )
        parser.add_argument(
            '--date',
            type=str,
            help='Дата в формате YYYY-MM-DD. По умолчанию — сегодня.'
        )
        parser.add_argument(
            '--current',
            action='store_true',
            help='Забрать все текущие незавершённые простои (без ограничения по дате)'
        )

    def handle(self, *args, **options):
        # Определяем даты смены
        begin_dt, end_dt, shift_type = self._get_shift_times(
            options.get('shift'),
            options.get('date')
        )
        self.stdout.write(
            f"Загрузка простоев за {shift_type} смену: "
            f"{begin_dt} → {end_dt}"
        )
        # Загружаем все страницы
        all_records = self._fetch_all_pages(begin_dt, end_dt)
        if not all_records:
            self.stdout.write(self.style.WARNING("Простоев не найдено."))
            return
        self.stdout.write(f"Получено записей из API: {len(all_records)}")
        uuid_to_oes = self._build_uuid_mapping()
        created, updated, skipped = self._save_records(
            all_records, uuid_to_oes, shift_type
        )
        self.stdout.write(self.style.SUCCESS(
            f"Готово! Создано: {created}, обновлено: {updated}, пропущено: {skipped}"
        ))

    def _get_shift_times(self, shift_arg, date_arg):
        """Вычисляет begin_dt и end_dt для запроса."""
        if date_arg:
            base_date = datetime.strptime(date_arg, '%Y-%m-%d').date()
        else:
            base_date = timezone.localtime().date()

        if shift_arg:
            shift_type = shift_arg
        else:
            # Автоопределение: если сейчас после 19:50 — дневная смена закончилась
            # Если сейчас после 07:50 но до 19:50 — ночная закончилась
            now = timezone.localtime()
            current_hour = now.hour
            if current_hour >= 19:
                shift_type = 'day'
            elif current_hour >= 7:
                shift_type = 'night'
            else:
                shift_type = 'night'
                base_date = base_date - timedelta(days=1)

        if shift_type == 'day':
            # Дневная: 07:45 → 19:45 того же дня
            begin_dt = datetime(
                base_date.year, base_date.month, base_date.day,
                DAY_SHIFT_START_HOUR, DAY_SHIFT_START_MIN, 0
            )
            end_dt = datetime(
                base_date.year, base_date.month, base_date.day,
                NIGHT_SHIFT_START_HOUR, NIGHT_SHIFT_START_MIN, 0
            )
        else:
            # Ночная: 19:45 предыдущего дня → 07:45 текущего дня
            prev_date = base_date - timedelta(days=1)
            begin_dt = datetime(
                prev_date.year, prev_date.month, prev_date.day,
                NIGHT_SHIFT_START_HOUR, NIGHT_SHIFT_START_MIN, 0
            )
            end_dt = datetime(
                base_date.year, base_date.month, base_date.day,
                DAY_SHIFT_START_HOUR, DAY_SHIFT_START_MIN, 0
            )

        return (
            begin_dt.strftime('%Y-%m-%d %H:%M:%S'),
            end_dt.strftime('%Y-%m-%d %H:%M:%S'),
            shift_type
        )

    def _fetch_all_pages(self, begin_dt, end_dt):
        """Забирает все страницы из API."""
        all_records = []
        page = 1

        while True:
            params = {
                **FIXED_PARAMS,
                "begin_dt": begin_dt,
                "end_dt": end_dt,
                "page": page,
            }

            try:
                self.stdout.write(f"  Запрос страницы {page}...")
                response = requests.post(API_URL, json=params, timeout=30)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка API на странице {page}: {e}")
                self.stdout.write(self.style.ERROR(f"Ошибка API: {e}"))
                break
            except ValueError as e:
                logger.error(f"Ошибка парсинга JSON: {e}")
                self.stdout.write(self.style.ERROR(f"Ошибка JSON: {e}"))
                break

            records = data.get('data', [])
            all_records.extend(records)

            total_pages = data.get('total_pages', 1)
            self.stdout.write(
                f"  Страница {page}/{total_pages}, "
                f"записей на странице: {len(records)}"
            )

            if page >= total_pages:
                break
            page += 1

        return all_records

    def _build_uuid_mapping(self):
        """Строит словарь mdm_object_uuid → OesObject."""
        mapping = {}
        for obj in OesObject.objects.filter(mdm_object_uuid__isnull=False):
            if obj.mdm_object_uuid:
                mapping[str(obj.mdm_object_uuid)] = obj
        return mapping

    def _parse_dt(self, dt_str):
        """Парсит дату из API и добавляет таймзону Сахалина."""
        if not dt_str:
            return None
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", ""))
            if dt.tzinfo is None:
                return SAKHALIN_TZ.localize(dt)
            return dt
        except (ValueError, TypeError):
            return None

    def _save_records(self, records, uuid_to_oes, shift_type):
        """Сохраняет записи в БД. Возвращает (created, updated, skipped)."""
        created = 0
        updated = 0
        skipped = 0

        for item in records:
            external_id = item.get('id')
            if not external_id:
                skipped += 1
                continue

            # Ищем связанный OesObject по UUID
            object_uuid = item.get('object_uuid')
            oes_object = None
            if object_uuid:
                # Убираем нулевые UUID
                if object_uuid != '00000-00000-00000-00000-00000':
                    oes_object = uuid_to_oes.get(str(object_uuid))

            # Подготавливаем данные
            defaults = {
                'oes_object': oes_object,
                'object_uuid': object_uuid if object_uuid and object_uuid != '00000-00000-00000-00000-00000' else None,
                'object_id_external': item.get('object_id'),
                'begin_dt': self._parse_dt(item.get('begin_dt')),
                'end_dt': self._parse_dt(item.get('end_dt')),
                'duration': item.get('duration'),
                'duration_from_shift': item.get('duration_from_shift'),
                'idle_type_id': item.get('idle_type_id'),
                'idle_type_name': item.get('idle_type_name', ''),
                'category_id': item.get('category_id'),
                'category_name': item.get('category_name', ''),
                'comment': item.get('comment', '') or '',
                'selected': item.get('selected', False),
                'is_manual': item.get('is_manual', False),
                'is_engine_on': item.get('is_engine_on', False),
                'is_allowed_zone': item.get('is_allowed_zone', False),
                'lat': str(item.get('lat', '')),
                'lon': str(item.get('lon', '')),
                'geozones': item.get('geozones', '') or '',
                'updated_by': item.get('updated_by', '') or '',
                'enterprise_id': item.get('enterprise_id'),
                'raw_data': item,
                'shift_type': shift_type,
            }

            try:
                _, was_created = IdleRecord.objects.update_or_create(
                    external_id=external_id,
                    defaults=defaults
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                logger.error(f"Ошибка сохранения записи {external_id}: {e}")
                skipped += 1

        return created, updated, skipped