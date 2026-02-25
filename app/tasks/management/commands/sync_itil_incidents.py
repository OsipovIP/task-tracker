import requests
import json
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import models
from tasks.models import Task
from requests_ntlm import HttpNtlmAuth

User = get_user_model()


class Command(BaseCommand):
    help = 'Синхронизирует инциденты из ITIL системы'

    def add_arguments(self, parser):
        parser.add_argument(
            '--url',
            type=str,
            default='http://1c02-app01/IT_ITIL/hs/api/v1/incident/',
            help='URL ITIL API'
        )
        parser.add_argument(
            '--try-alternative-urls',
            action='store_true',
            help='Попробовать альтернативные URL'
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Имя пользователя для авторизации'
        )
        parser.add_argument(
            '--password',
            type=str,
            help='Пароль для авторизации'
        )
        parser.add_argument(
            '--token',
            type=str,
            help='Токен для авторизации'
        )
        parser.add_argument(
            '--service-filter',
            type=str,
            default='Поддержка УАПП',
            help='Фильтр по услуге (по умолчанию: Поддержка УАПП)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать, что будет синхронизировано, без сохранения'
        )

    def handle(self, *args, **options):
        url = options['url']
        username = options.get('username')
        password = options.get('password')
        token = options.get('token')
        service_filter = options['service_filter']
        dry_run = options['dry_run']
        try_alternative_urls = options['try_alternative_urls']

        self.stdout.write(
            self.style.SUCCESS(f'Начинаем синхронизацию ITIL инцидентов...')
        )
        self.stdout.write(f'URL: {url}')
        self.stdout.write(f'Фильтр по услуге: {service_filter}')

        try:
            # Получаем данные из API
            if try_alternative_urls:
                incidents_data = self.try_multiple_urls(username, password, token)
            else:
                incidents_data = self.fetch_itil_data(url, username, password, token)
            
            if not incidents_data:
                self.stdout.write(
                    self.style.WARNING('Данные не получены из ITIL API')
                )
                return

            # Фильтруем по услуге
            filtered_incidents = self.filter_incidents_by_service(
                incidents_data, service_filter
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Найдено {len(filtered_incidents)} инцидентов с услугой "{service_filter}"'
                )
            )

            if dry_run:
                self.show_dry_run_results(filtered_incidents)
                return

            # Синхронизируем данные
            synced_count = self.sync_incidents(filtered_incidents)

            self.stdout.write(
                self.style.SUCCESS(
                    f'Синхронизация завершена. Обработано {synced_count} инцидентов'
                )
            )

        except Exception as e:
            raise CommandError(f'Ошибка при синхронизации: {str(e)}')

    def try_multiple_urls(self, username=None, password=None, token=None):
        """Пробует разные варианты URL для подключения к API"""
        alternative_urls = [
            'http://1c02-app01/IT_ITIL/hs/api/v1/incident/',
            'http://1c02-app01/IT_ITIL/hs/api/v1/incident',
            'http://1c02-app01/IT_ITIL/hs/api/v1/incidents/',
            'http://1c02-app01/IT_ITIL/hs/api/incident/',
            'http://1c02-app01/IT_ITIL/hs/api/incident',
            'http://1c02-app01/IT_ITIL/hs/odata/incident/',
            'http://1c02-app01/IT_ITIL/hs/odata/incidents/',
        ]
        
        for url in alternative_urls:
            self.stdout.write(f'Пробуем URL: {url}')
            try:
                data = self.fetch_itil_data(url, username, password, token)
                if data:
                    self.stdout.write(self.style.SUCCESS(f'Успешно подключились к: {url}'))
                    return data
            except Exception as e:
                self.stdout.write(f'Не удалось подключиться к {url}: {str(e)}')
                continue
        
        self.stdout.write(self.style.ERROR('Не удалось подключиться ни к одному URL'))
        return []

    def fetch_itil_data(self, url, username=None, password=None, token=None):
        """Получает данные из ITIL API"""
        try:
            # Настройка авторизации и заголовков
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'TaskTracker/1.0'
            }
            
            auth = None
            if username and password:
                # Используем NTLM авторизацию для Windows сервера
                auth = HttpNtlmAuth(username, password)
            
            if token:
                headers['Authorization'] = f'Bearer {token}'

            self.stdout.write(f'Пытаемся подключиться к: {url}')
            self.stdout.write(f'Пользователь: {username}')
            self.stdout.write(f'Используем токен: {bool(token)}')

            response = requests.get(url, auth=auth, headers=headers, timeout=30)
            self.stdout.write(f'Статус ответа: {response.status_code}')
            
            if response.status_code == 401:
                self.stdout.write('Ошибка авторизации. Попробуйте:')
                self.stdout.write('1. Проверить логин/пароль')
                self.stdout.write('2. Использовать токен: --token YOUR_TOKEN')
                self.stdout.write('3. Проверить права доступа к API')
            
            response.raise_for_status()

            # Парсим JSON
            data = response.json()
            
            # Проверяем, что данные в правильном формате
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'data' in data:
                return data['data']
            else:
                self.stdout.write(
                    self.style.WARNING('Неожиданный формат данных от API')
                )
                return []

        except requests.exceptions.RequestException as e:
            raise CommandError(f'Ошибка при запросе к ITIL API: {str(e)}')
        except json.JSONDecodeError as e:
            raise CommandError(f'Ошибка при парсинге JSON: {str(e)}')

    def filter_incidents_by_service(self, incidents_data, service_filter):
        """Фильтрует инциденты по услуге"""
        filtered = []
        
        for incident in incidents_data:
            if incident.get('Документ_Услуга') == service_filter:
                filtered.append(incident)
        
        return filtered

    def show_dry_run_results(self, incidents):
        """Показывает результаты в режиме dry-run"""
        self.stdout.write(self.style.WARNING('=== DRY RUN РЕЗУЛЬТАТЫ ==='))
        
        for i, incident in enumerate(incidents[:10], 1):  # Показываем первые 10
            self.stdout.write(f'{i}. {incident.get("Документ_ID", "N/A")} - {incident.get("Документ_Услуга", "N/A")}')
            self.stdout.write(f'   Статус: {incident.get("Документ_Статус", "N/A")}')
            self.stdout.write(f'   Исполнитель: {incident.get("Документ_Текущий исполнитель", "N/A")}')
            self.stdout.write(f'   Приоритет: {incident.get("Документ_Приоритет", "N/A")}')
            self.stdout.write('')

        if len(incidents) > 10:
            self.stdout.write(f'... и еще {len(incidents) - 10} инцидентов')

    def sync_incidents(self, incidents_data):
        """Синхронизирует инциденты с базой данных как Task объекты"""
        synced_count = 0
        created_count = 0
        updated_count = 0
        
        for incident_data in incidents_data:
            try:
                # Парсим данные инцидента
                incident_id = incident_data.get('Документ_ID')
                if not incident_id:
                    continue

                # Парсим даты
                document_date = self.parse_datetime(
                    incident_data.get('Документ_Дата')
                )
                deadline = self.parse_datetime(
                    incident_data.get('Документ_Крайний срок устранения')
                )

                # Маппинг приоритета из ITIL в Task
                priority_map = {
                    'Критический': Task.PRIORITY_CRITICAL,
                    'Высокий': Task.PRIORITY_HIGH,
                    'Средний': Task.PRIORITY_MEDIUM,
                    'Низкий': Task.PRIORITY_LOW,
                }
                itil_priority = incident_data.get('Документ_Приоритет', 'Средний')
                priority = priority_map.get(itil_priority, Task.PRIORITY_MEDIUM)

                # Маппинг статуса из ITIL в Task
                status_map = {
                    'Зарегистрирован': Task.STATUS_TODO,
                    'Принят к выполнению': Task.STATUS_IN_PROGRESS,
                    'Эскалация': Task.STATUS_WAITING,
                    'Выполнен': Task.STATUS_DONE,
                    'Закрыт': Task.STATUS_DONE,
                }
                itil_status = incident_data.get('Документ_Статус', 'Зарегистрирован')
                status = status_map.get(itil_status, Task.STATUS_TODO)

                # Формируем заголовок и описание
                service = incident_data.get('Документ_Услуга', '')
                initiator = incident_data.get('Документ_Инициатор', '')
                title = f"ITIL: {service} - {initiator}"

                description_parts = [
                    f"**Инициатор:** {initiator}",
                    f"**Организация:** {incident_data.get('Документ_Организация инициатора', '')}",
                    f"**Текущий исполнитель:** {incident_data.get('Документ_Текущий исполнитель', '')}",
                    f"**Этап:** {incident_data.get('Текущий_Этап', '')}",
                    f"**Маршрут:** {incident_data.get('Документ_Маршрут', '')}",
                    f"**Приоритет ITIL:** {itil_priority}",
                    f"**Статус ITIL:** {itil_status}",
                ]
                
                if incident_data.get('Документ_Превышен срок решения') == 'Да':
                    description_parts.insert(0, "⚠️ **СРОК РЕШЕНИЯ ПРЕВЫШЕН!**")
                
                description = "\n".join(description_parts)

                # Находим или создаем исполнителя
                executor_name = incident_data.get('Документ_Текущий исполнитель', '').strip()
                assigned_user = None
                if executor_name and executor_name != 'Поддержка УАПП':
                    # Пытаемся найти пользователя по имени
                    # Можно улучшить, создав маппинг имен на username
                    try:
                        assigned_user = User.objects.filter(
                            models.Q(first_name__icontains=executor_name.split()[0]) |
                            models.Q(last_name__icontains=executor_name.split()[-1])
                        ).first()
                    except Exception:
                        pass

                # Создаем или обновляем задачу
                task, created = Task.objects.update_or_create(
                    external_source='ITIL',
                    external_id=incident_id,
                    defaults={
                        'title': title,
                        'description': description,
                        'status': status,
                        'priority': priority,
                        'due_date': deadline,
                        'assigned_to': assigned_user,
                        'external_data': incident_data,  # Сохраняем все исходные данные
                    }
                )

                if created:
                    created_count += 1
                    action = "Создана"
                else:
                    updated_count += 1
                    action = "Обновлена"
                
                self.stdout.write(
                    self.style.SUCCESS(f'{action} задача: #{task.id} - {title[:50]}...')
                )
                synced_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Ошибка при обработке инцидента {incident_data.get("Документ_ID", "N/A")}: {str(e)}')
                )
                import traceback
                self.stdout.write(traceback.format_exc())

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Итого: создано {created_count}, обновлено {updated_count}'))
        return synced_count

    def parse_datetime(self, date_string):
        """Парсит дату из строки"""
        if not date_string or date_string == '0001-01-01T00:00:00':
            return None
        
        try:
            # Парсим ISO формат: 2025-09-19T18:12:28
            return datetime.fromisoformat(date_string.replace('T', ' '))
        except (ValueError, AttributeError):
            return None
