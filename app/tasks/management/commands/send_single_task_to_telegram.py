"""
Management команда для отправки одной задачи в Telegram группу
"""
from django.core.management.base import BaseCommand
import os
import logging
from telegram import Bot
import asyncio

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send single task to Telegram group'

    def add_arguments(self, parser):
        parser.add_argument('task_id', type=int, help='Task ID to send')

    def handle(self, *args, **options):
        try:
            from tasks.models import Task
            
            task_id = options['task_id']
            
            # Получаем задачу
            try:
                task = Task.objects.select_related('assigned_to', 'oes_object', 'oes_object__model').get(id=task_id)
            except Task.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Task with ID {task_id} not found'))
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
                text = text.replace('&', '&amp;')
                text = text.replace('<', '&lt;')
                text = text.replace('>', '&gt;')
                return text
            
            # Формируем сообщение для одной задачи
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
            
            message = f"{asset} - {description} - {assignee}"
            
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
                f'Single task {task_id} sent to Telegram group (topic {topic_id})'
            ))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
            logger.error(f"Error sending single task: {e}", exc_info=True)

