"""
Клиент для безопасных запросов к ClickHouse.

Все запросы:
- Ограничены по времени (последний час)
- Используют только агрегаты (COUNT, MAX, MIN, AVG)
- Фильтруют по конкретным объектам
- Не тянут сырые строки
"""

import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Значение "нет данных" в ClickHouse (дефолт для большинства колонок)
CH_NO_DATA_VALUE = -1000000


class ClickHouseClient:
    """Безопасный read-only клиент для ClickHouse через HTTP."""
    
    def __init__(self):
        self.host = settings.CLICKHOUSE_HOST
        self.port = settings.CLICKHOUSE_PORT
        self.user = settings.CLICKHOUSE_USER
        self.password = settings.CLICKHOUSE_PASSWORD
        self.database = settings.CLICKHOUSE_DB
        self.base_url = f"http://{self.host}:{self.port}/"
    
    def _execute(self, query, timeout=10):
        """Выполняет запрос к ClickHouse. Возвращает список строк."""
        params = {
            'database': self.database,
            'query': query,
            'user': self.user,
            'password': self.password,
        }
        
        try:
            response = requests.get(
                self.base_url,
                params=params,
                timeout=timeout
            )
            response.raise_for_status()
            
            # Парсим TSV ответ
            text = response.text.strip()
            if not text:
                return []
            
            rows = []
            for line in text.split('\n'):
                rows.append(line.split('\t'))
            return rows
            
        except requests.exceptions.Timeout:
            logger.error(f"ClickHouse timeout: {query[:200]}")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"ClickHouse error: {e}")
            return []
    
    def check_tags_batch(self, table, object_uuids, tag_configs, hours=1):
        """
        Проверяет теги для пачки объектов за последний час.
        
        Args:
            table: 'trucks' или 'heavy_equipment'
            object_ids: список source_id (mdm_object_id) объектов
            tag_configs: список ModelTagConfig объектов
            hours: за сколько часов проверять (по умолчанию 1)
        
        Returns:
            dict: {
                source_id: {
                    'tag_name': {
                        'status': 'ok' | 'fail' | 'warn',
                        'detail': 'описание',
                        'values': {...}
                    }
                }
            }
        """
        if not object_uuids or not tag_configs:

            return {}
        
        # Собираем уникальные теги
        tag_names = list(set(tc.tag_name for tc in tag_configs))
        
        # Формируем SELECT: для каждого тега берём count, min, max, avg
        # но только для значений ≠ -1000000 (есть данные)
        select_parts = ['mdm_object_uuid']
        select_parts.append('count() as total_rows')
        
        for tag in tag_names:
            safe_tag = tag  # tag_name уже проверен через модель
            select_parts.append(
                f"countIf({safe_tag} != {CH_NO_DATA_VALUE}) as cnt_{safe_tag}"
            )
            select_parts.append(
                f"minIf({safe_tag}, {safe_tag} != {CH_NO_DATA_VALUE}) as min_{safe_tag}"
            )
            select_parts.append(
                f"maxIf({safe_tag}, {safe_tag} != {CH_NO_DATA_VALUE}) as max_{safe_tag}"
            )
            select_parts.append(
                f"avgIf({safe_tag}, {safe_tag} != {CH_NO_DATA_VALUE}) as avg_{safe_tag}"
            )
        
        # Формируем запрос
        ids_str = ','.join(f"'{uid}'" for uid in object_uuids)
        
        query = (
            f"SELECT {', '.join(select_parts)} "
            f"FROM telemetry.{table} "
            f"WHERE mdm_object_uuid IN ({ids_str}) "
            f"AND create_dt >= now() - INTERVAL {int(hours)} HOUR "
            f"GROUP BY mdm_object_uuid"
        )
        
        logger.info(f"ClickHouse query: {query[:300]}...")
        
        rows = self._execute(query, timeout=15)
        
        if not rows:
            # Нет данных вообще — все объекты fail
            result = {}
            for uid in object_uuids:
                result[uid] = {}
                for tc in tag_configs:
                    result[uid][tc.tag_name] = {
                        'status': 'fail',
                        'detail': 'Нет данных из ClickHouse за последний час',
                        'values': {}
                    }
            return result
        
        # Парсим заголовки
        # Порядок: mdm_object_id, total_rows, cnt_tag1, min_tag1, max_tag1, avg_tag1, ...
        result = {}
        
        # Индексы колонок
        col_idx = {}
        col_idx['mdm_object_id'] = 0
        col_idx['total_rows'] = 1
        offset = 2
        for tag in tag_names:
            col_idx[f'cnt_{tag}'] = offset
            col_idx[f'min_{tag}'] = offset + 1
            col_idx[f'max_{tag}'] = offset + 2
            col_idx[f'avg_{tag}'] = offset + 3
            offset += 4
        
        # Заполняем данные из ClickHouse
        found_ids = set()
        for row in rows:
            try:
                uid = row[0]
                found_ids.add(uid)
                result[uid] = {}
                
                total_rows = int(row[col_idx['total_rows']])
                
                for tc in tag_configs:
                    tag = tc.tag_name
                    cnt = int(row[col_idx[f'cnt_{tag}']])
                    
                    if cnt == 0:
                        # Нет валидных данных по этому тегу
                        result[uid][tag] = {
                            'status': 'fail',
                            'detail': f'Нет данных по тегу {tag} (все значения = -1000000)',
                            'values': {'count': 0, 'total_rows': total_rows}
                        }
                        continue
                    
                    min_val = float(row[col_idx[f'min_{tag}']])
                    max_val = float(row[col_idx[f'max_{tag}']])
                    avg_val = float(row[col_idx[f'avg_{tag}']])
                    
                    values = {
                        'count': cnt,
                        'min': min_val,
                        'max': max_val,
                        'avg': avg_val,
                        'total_rows': total_rows
                    }
                    
                    # Проверяем по типу
                    status, detail = self._check_tag_value(tc, values)
                    
                    result[uid][tag] = {
                        'status': status,
                        'detail': detail,
                        'values': values
                    }
                    
            except (IndexError, ValueError) as e:
                logger.error(f"Error parsing CH row: {e}, row={row}")
                continue
        
        # Объекты, которых нет в ClickHouse вообще
        for uid in object_uuids:
            if uid not in found_ids:
                result[uid] = {}
                for tc in tag_configs:
                    result[uid][tc.tag_name] = {
                        'status': 'fail',
                        'detail': 'Объект не найден в ClickHouse за последний час',
                        'values': {}
                    }
        
        return result
    
    def _check_tag_value(self, tag_config, values):
        """
        Проверяет значения тега по конфигурации.
        
        Returns:
            (status, detail): status = 'ok' | 'fail' | 'warn'
        """
        cnt = values['count']
        min_val = values['min']
        max_val = values['max']
        avg_val = values['avg']
        
        if tag_config.check_type == 'exists':
            # Просто наличие данных
            if cnt > 0:
                return 'ok', f'Данные есть ({cnt} записей, avg={avg_val:.2f})'
            return 'fail', 'Нет данных'
        
        elif tag_config.check_type == 'threshold_min':
            # Минимальное значение должно быть >= порога
            if min_val >= tag_config.threshold_min:
                return 'ok', f'Мин={min_val:.2f} ≥ {tag_config.threshold_min}'
            return 'warn', f'Мин={min_val:.2f} < порога {tag_config.threshold_min}'
        
        elif tag_config.check_type == 'threshold_max':
            # Максимальное значение должно быть <= порога
            if max_val <= tag_config.threshold_max:
                return 'ok', f'Макс={max_val:.2f} ≤ {tag_config.threshold_max}'
            return 'warn', f'Макс={max_val:.2f} > порога {tag_config.threshold_max}'
        
        elif tag_config.check_type == 'threshold_range':
            # Значение должно быть в диапазоне
            if min_val >= tag_config.threshold_min and max_val <= tag_config.threshold_max:
                return 'ok', f'В диапазоне [{tag_config.threshold_min}, {tag_config.threshold_max}]'
            detail_parts = []
            if min_val < tag_config.threshold_min:
                detail_parts.append(f'мин={min_val:.2f} < {tag_config.threshold_min}')
            if max_val > tag_config.threshold_max:
                detail_parts.append(f'макс={max_val:.2f} > {tag_config.threshold_max}')
            return 'warn', f'Выход за диапазон: {", ".join(detail_parts)}'
        
        elif tag_config.check_type == 'change':
            # Значение должно меняться
            delta = abs(max_val - min_val)
            if delta >= tag_config.min_change:
                return 'ok', f'Изменение={delta:.6f} ≥ {tag_config.min_change}'
            return 'fail', f'Нет изменений: дельта={delta:.6f} < {tag_config.min_change}'
        
        return 'ok', 'Неизвестный тип проверки'
    
    def test_connection(self):
        """Проверка подключения к ClickHouse."""
        try:
            rows = self._execute("SELECT 1", timeout=5)
            return rows is not None and len(rows) > 0
        except Exception as e:
            logger.error(f"ClickHouse connection test failed: {e}")
            return False
