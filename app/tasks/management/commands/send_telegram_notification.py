"""
Management команда для отправки уведомлений в Telegram
"""
from django.core.management.base import BaseCommand
import os
import json
import logging
from telegram import Bot
import asyncio

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send task notification to user via Telegram'

    def add_arguments(self, parser):
        parser.add_argument('user_id', type=int, help='Django user ID')
        parser.add_argument('task_id', type=int, help='Task ID')

    def handle(self, *args, **options):
        user_id = options['user_id']
        task_id = options['task_id']
        
        try:
            from tasks.models import Task
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            task = Task.objects.get(id=task_id)
            
            # Загружаем маппинг
            mapping_file = '/tmp/telegram_user_mapping.json'
            user_mapping = {}
            
            if os.path.exists(mapping_file):
                with open(mapping_file, 'r') as f:
                    data = json.load(f)
                    user_mapping = {int(k): v for k, v in data.items()}
            
            # Ищем telegram_id
            telegram_id = None
            for t_id, u_id in user_mapping.items():
                if u_id == user_id:
                    telegram_id = t_id
                    break
            
            if not telegram_id:
                self.stdout.write(self.style.WARNING(
                    f'User {user_id} not found in Telegram mapping'
                ))
                return
            
            # Получаем токен
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            if not bot_token:
                self.stdout.write(self.style.ERROR('TELEGRAM_BOT_TOKEN not set'))
                return
            
            # Формируем сообщение
            message = f"🔔 *Вам назначена новая задача!*\n\n"
            message += f"📋 *Задача #{task.id}*\n"
            message += f"*Заголовок:* {task.title}\n"
            
            if task.description:
                desc = task.description[:200]
                if len(task.description) > 200:
                    desc += "..."
                message += f"*Описание:* {desc}\n"
            
            message += f"*Статус:* {task.get_status_display()}\n"
            message += f"*Приоритет:* {task.get_priority_display()}\n"
            
            if task.oes_object:
                message += f"*Актив:* {task.oes_object.name}\n"
            
            if task.due_date:
                due_date_str = task.due_date.strftime('%d.%m.%Y %H:%M')
                message += f"*Срок:* {due_date_str}\n"
            
            # Отправляем
            async def send():
                bot = Bot(token=bot_token)
                await bot.send_message(
                    chat_id=telegram_id,
                    text=message,
                    parse_mode='Markdown'
                )
            
            asyncio.run(send())
            
            self.stdout.write(self.style.SUCCESS(
                f'Notification sent to user {user_id} (telegram_id: {telegram_id})'
            ))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
            logger.error(f"Error sending notification: {e}", exc_info=True)


