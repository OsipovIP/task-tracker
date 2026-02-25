"""
Модуль для отправки уведомлений в Telegram из Django
"""
import os
import logging
import asyncio
from telegram import Bot

logger = logging.getLogger(__name__)

# Загружаем маппинг пользователей из основного модуля бота
try:
    from telegram_bot.bot import user_mapping
except ImportError:
    user_mapping = {}
    logger.warning("Could not import user_mapping from bot")


def send_task_notification(user_id, task):
    """
    Синхронная обертка для отправки уведомления о назначенной задаче
    
    Args:
        user_id: ID пользователя Django
        task: Объект задачи Task
    """
    try:
        # Получаем токен бота
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not set, skipping notification")
            return
        
        # Ищем telegram_id по user_id
        logger.info(f"Looking for telegram_id for user_id {user_id}")
        logger.info(f"Current user_mapping: {user_mapping}")
        
        telegram_id = None
        for t_id, u_id in user_mapping.items():
            if u_id == user_id:
                telegram_id = t_id
                break
        
        if not telegram_id:
            logger.warning(f"Telegram ID not found for user_id {user_id}, user not authorized in bot")
            return
        
        logger.info(f"Found telegram_id {telegram_id} for user_id {user_id}")
        
        # Создаем бота
        bot = Bot(token=bot_token)
        
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
        
        # Отправляем уведомление асинхронно
        async def send():
            await bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode='Markdown'
            )
        
        # Запускаем в event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(send())
        logger.info(f"Notification sent to user {user_id} (telegram_id: {telegram_id}) about task #{task.id}")
        
    except Exception as e:
        logger.error(f"Error sending task notification: {e}", exc_info=True)

