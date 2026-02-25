"""
Management команда для отправки наряда в Telegram группу
"""
from django.core.management.base import BaseCommand
import os
import logging
from telegram import Bot
import asyncio

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send work order to Telegram group'

    def handle(self, *args, **options):
        try:
            from tasks.models import Task
            
            # Получаем задачи со статусом "К выполнению" и "В работе"
            tasks = Task.objects.filter(
                status__in=[Task.STATUS_TODO, Task.STATUS_IN_PROGRESS]
            ).select_related('assigned_to', 'oes_object').order_by('-created_at')
            
            if not tasks:
                self.stdout.write(self.style.WARNING('No tasks found'))
                return
            
            # Получаем настройки группы
            group_id = os.getenv('NOTIFICATION_GROUP_ID')
            topic_id = os.getenv('WORK_ORDER_TOPIC_ID', '3')  # ID темы для нарядов (по умолчанию 3)
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            
            if not group_id or not bot_token:
                self.stdout.write(self.style.ERROR('NOTIFICATION_GROUP_ID or TELEGRAM_BOT_TOKEN not set'))
                return
            
            # Функция для экранирования HTML символов
            def escape_html(text):
                if not text:
                    return ""
                # Экранируем HTML символы
                text = text.replace('&', '&amp;')
                text = text.replace('<', '&lt;')
                text = text.replace('>', '&gt;')
                return text
            
            # Формируем сообщение
            from datetime import datetime
            
            message_lines = []
            
            # Добавляем заголовок с датой
            current_date = datetime.now().strftime("%d.%m.%Y")
            message_lines.append(f"📋 <b>Группа КИП</b> - {current_date}")
            message_lines.append("")
            
            for task in tasks:
                # Формат: актив - описание - исполнитель
                if task.oes_object:
                    asset = task.oes_object.name
                    if task.oes_object.model:
                        asset = f"{asset} {task.oes_object.model.name}"
                    asset = f"<b>{escape_html(asset)}</b>"  # Жирный
                else:
                    asset = "<b>без актива</b>"
                
                description = task.description if task.description else task.title
                description = escape_html(description)
                
                # Используем First name + Last name, если есть, иначе username
                if task.assigned_to:
                    if task.assigned_to.first_name or task.assigned_to.last_name:
                        assignee = f"{task.assigned_to.first_name} {task.assigned_to.last_name}".strip()
                    else:
                        assignee = task.assigned_to.username
                    assignee = f"<i>{escape_html(assignee)}</i>"  # Курсив
                else:
                    assignee = "<i>не назначена</i>"
                
                line = f"{asset} - {description} - {assignee}"
                
                message_lines.append(line)
                message_lines.append("")
            
            message = "\n".join(message_lines)
            
            # Отправляем
            async def send():
                bot = Bot(token=bot_token)
                await bot.send_message(
                    chat_id=group_id,
                    message_thread_id=int(topic_id),
                    text=message,
                    parse_mode='HTML'
                )
            
            asyncio.run(send())
            
            self.stdout.write(self.style.SUCCESS(
                f'Work order sent to Telegram group (topic {topic_id})'
            ))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
            logger.error(f"Error sending work order: {e}", exc_info=True)

