"""
Telegram бот для Task Tracker
Позволяет просматривать и закрывать задачи через Telegram
"""

import os
import sys
import django
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from asgiref.sync import sync_to_async
from django.utils import timezone

# Настройка Django
sys.path.insert(0, '/usr/src/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_tracker.settings')
django.setup()

from django.contrib.auth import get_user_model
from tasks.models import Task, TaskComment, TaskCompletionReport, TaskPhoto, FaultCategory
from django.conf import settings
from datetime import timedelta
import uuid
import re

User = get_user_model()

# Функция для экранирования специальных символов Markdown
def escape_markdown(text):
    """Экранирует специальные символы Markdown v2"""
    if text is None:
        return ""
    text = str(text)
    # Экранируем специальные символы Markdown
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    # Дополнительно экранируем переносы строк
    text = text.replace('\n', ' ')
    # Ограничиваем длину текста для избежания ошибок парсинга
    if len(text) > 1000:
        text = text[:997] + '...'
    return text

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Хранилище данных пользователей (telegram_id -> user_id)
user_mapping = {}

# Файл для хранения маппинга
MAPPING_FILE = '/tmp/telegram_user_mapping.json'

# Загружаем маппинг из файла при старте
def load_user_mapping():
    global user_mapping
    try:
        if os.path.exists(MAPPING_FILE):
            import json
            with open(MAPPING_FILE, 'r') as f:
                data = json.load(f)
                # Конвертируем ключи обратно в int
                user_mapping = {int(k): v for k, v in data.items()}
            logger.info(f"Loaded user mapping: {user_mapping}")
    except Exception as e:
        logger.error(f"Error loading user mapping: {e}")

# Сохраняем маппинг в файл
def save_user_mapping():
    try:
        import json
        with open(MAPPING_FILE, 'w') as f:
            json.dump(user_mapping, f)
        logger.info(f"Saved user mapping: {user_mapping}")
    except Exception as e:
        logger.error(f"Error saving user mapping: {e}")

# Настройки группы для уведомлений
NOTIFICATION_GROUP_ID = os.getenv('NOTIFICATION_GROUP_ID')  # ID группы (например: -1001234567890)
NOTIFICATION_TOPIC_ID = os.getenv('NOTIFICATION_TOPIC_ID')  # ID темы в группе (необязательно)


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def send_new_task_notification(bot, user_id, task):
    """Отправляет уведомление пользователю о новой назначенной задаче"""
    try:
        # Ищем telegram_id по user_id
        telegram_id = None
        for t_id, u_id in user_mapping.items():
            if u_id == user_id:
                telegram_id = t_id
                break
        
        if not telegram_id:
            logger.warning(f"Telegram ID not found for user_id {user_id}")
            return
        
        # Формируем сообщение
        message = f"🔔 *Вам назначена новая задача!*\n\n"
        message += f"📋 *Задача #{task.id}*\n"
        message += f"*Заголовок:* {escape_markdown(task.title)}\n"
        
        if task.description:
            message += f"*Описание:* {escape_markdown(task.description[:200])}\n"
        
        message += f"*Статус:* {escape_markdown(task.get_status_display())}\n"
        message += f"*Приоритет:* {escape_markdown(task.get_priority_display())}\n"
        
        if task.oes_object:
            message += f"*Актив:* {escape_markdown(task.oes_object.name)}\n"
        
        if task.due_date:
            due_date_str = task.due_date.strftime('%d.%m.%Y %H:%M')
            message += f"*Срок:* {due_date_str}\n"
        
        # Отправляем уведомление
        await bot.send_message(
            chat_id=telegram_id,
            text=message,
            parse_mode='Markdown'
        )
        logger.info(f"Notification sent to user {user_id} (telegram_id: {telegram_id}) about task #{task.id}")
        
    except Exception as e:
        logger.error(f"Error sending task notification: {e}", exc_info=True)


async def send_task_closure_to_group(context, task, user, work_done, fault_category, root_cause, time_spent, photos):
    """Отправляет уведомление о закрытии задачи в группу"""
    if not NOTIFICATION_GROUP_ID:
        logger.warning("NOTIFICATION_GROUP_ID not set, skipping group notification")
        return
    
    try:
        # Получаем связанные объекты асинхронно
        oes_object = await sync_to_async(lambda: task.oes_object if hasattr(task, 'oes_object') else None)()
        oes_name = await sync_to_async(lambda: oes_object.name if oes_object else None)()
        
        # Формируем текст сообщения
        # Получаем имя пользователя
        @sync_to_async
        def get_user_display_name(u):
            if u.first_name or u.last_name:
                return f"{u.first_name} {u.last_name}".strip()
            return u.username
        
        user_display_name = await get_user_display_name(user)
        
        # Получаем модель актива
        oes_model_name = None
        if oes_object:
            @sync_to_async
            def get_model_name(obj):
                try:
                    if hasattr(obj, 'model') and obj.model:
                        return obj.model.name
                except:
                    pass
                return None
            
            oes_model_name = await get_model_name(oes_object)
        
        message_lines = [
            f"Задача № {task.id} Закрыта",
            f"",
            f"Исполнитель: {escape_markdown(user_display_name)}",
        ]
        
        # Актив: Имя - Модель
        if oes_name:
            if oes_model_name:
                message_lines.append(f"Актив: {escape_markdown(oes_name)} - {escape_markdown(oes_model_name)}")
            else:
                message_lines.append(f"Актив: {escape_markdown(oes_name)}")
        
        # Категория
        if fault_category:
            category_name = await sync_to_async(lambda: fault_category.name)()
            message_lines.append(f"Категория: {escape_markdown(category_name)}")
        
        # Номер ITIL
        if task.itil_number:
            message_lines.append(f"Номер ITIL: {escape_markdown(task.itil_number)}")
        
        # Выполненная работа
        message_lines.extend([
            f"Выполненная работа:",
            f"{escape_markdown(work_done)}",
        ])
        
        # Корневая причина
        if root_cause and root_cause != 'Не указано':
            message_lines.append(f"Корневая причина: {escape_markdown(root_cause)}")
        
        # Затрачено время
        if time_spent:
            total_seconds = int(time_spent.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            if hours > 0 and minutes > 0:
                time_str = f"{hours} ч {minutes} мин"
            elif hours > 0:
                time_str = f"{hours} ч"
            else:
                time_str = f"{minutes} мин"
            message_lines.append(f"Затрачено: {time_str}")
        
        # Дополнительные исполнители
        @sync_to_async
        def get_additional_assignees():
            return list(task.additional_assignees.all())
        
        additional_assignees = await get_additional_assignees()
        if additional_assignees:
            @sync_to_async
            def get_assignee_name(u):
                if u.first_name or u.last_name:
                    return f"{u.first_name} {u.last_name}".strip()
                return u.username
            
            assignee_names = [await get_assignee_name(u) for u in additional_assignees]
            message_lines.append(f"Доп. Исполнители: {escape_markdown(', '.join(assignee_names))}")
        
        message_text = "\n".join(message_lines)
        
        # Параметры отправки
        send_kwargs = {
            'chat_id': NOTIFICATION_GROUP_ID,
            'parse_mode': 'Markdown'
        }
        
        # Если указан topic ID, добавляем его (проверяем, что тема существует)
        if NOTIFICATION_TOPIC_ID and NOTIFICATION_TOPIC_ID != '1':
            send_kwargs['message_thread_id'] = int(NOTIFICATION_TOPIC_ID)
        
        # Отправляем сообщение с фотографиями или без
        if photos and len(photos) > 0:
            # Если есть фотографии, отправляем медиа-группу
            from telegram import InputMediaPhoto
            
            media_group = []
            for i, photo_data in enumerate(photos):
                if i == 0:
                    # Первое фото с подписью
                    media_group.append(
                        InputMediaPhoto(
                            media=photo_data['file_id'],
                            caption=message_text,
                            parse_mode='Markdown'
                        )
                    )
                else:
                    # Остальные фото без подписи
                    media_group.append(
                        InputMediaPhoto(media=photo_data['file_id'])
                    )
            
            send_kwargs['media'] = media_group
            await context.bot.send_media_group(**send_kwargs)
            logger.info(f"Sent task closure notification to group with {len(photos)} photos")
        else:
            # Без фотографий
            send_kwargs['text'] = message_text
            await context.bot.send_message(**send_kwargs)
            logger.info("Sent task closure notification to group without photos")
            
    except Exception as e:
        logger.error(f"Error sending notification to group: {e}", exc_info=True)


# --- ФУНКЦИИ КЛАВИАТУРЫ ---

def get_main_keyboard(is_manager=False):
    """Возвращает главную клавиатуру"""
    keyboard = [
        [KeyboardButton("📋 Мои задачи")],
        [KeyboardButton("📄 Весь наряд")],
    ]
    if is_manager:
        keyboard.append([KeyboardButton("🔍 Задачи на проверке")])
    keyboard.append([KeyboardButton("ℹ️ Помощь")])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_auth_keyboard():
    """Возвращает клавиатуру для неавторизованных"""
    keyboard = [[KeyboardButton("ℹ️ Помощь")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# --- КОМАНДЫ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    telegram_id = update.effective_user.id
    
    if telegram_id in user_mapping:
        # Пользователь авторизован
        user_id = user_mapping[telegram_id]
        user = await sync_to_async(User.objects.get)(id=user_id)
        
        @sync_to_async
        def is_manager():
            return user.groups.filter(name='Менеджеры').exists()
        
        keyboard = get_main_keyboard(await is_manager())
        
        await update.message.reply_text(
            f"👋 С возвращением, {user.username}!\n\n"
            "Выберите действие:",
            reply_markup=keyboard
        )
    else:
        # Пользователь не авторизован
        keyboard = get_auth_keyboard()
        await update.message.reply_text(
            "👋 Добро пожаловать в Task Tracker Bot!\n\n"
            "Для начала работы привяжите свой аккаунт:\n"
            "/login <username> <password>",
            reply_markup=keyboard
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "📖 Доступные команды:\n\n"
        "/login <username> <password> - Авторизация\n"
        "/tasks - Список моих задач\n"
        "/checking - Задачи на проверке\n"
        "/cancel - Отменить текущее действие\n"
        "/help - Эта справка\n\n"
        "Для работы с задачей нажмите на нее в списке."
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущего действия (например, закрытия задачи)"""
    if 'closing_task_id' in context.user_data:
        task_id = context.user_data.pop('closing_task_id')
        context.user_data.pop('work_done', None)
        context.user_data.pop('fault_category_id', None)
        context.user_data.pop('root_cause', None)
        context.user_data.pop('time_spent', None)
        context.user_data.pop('additional_assignees', None)
        context.user_data.pop('photos', None)
        logger.info(f"User {update.effective_user.id} cancelled task closure for task {task_id}")
        await update.message.reply_text(
            f"❌ Процесс закрытия задачи #{task_id} отменен.\n\n"
            "Вы можете начать заново."
        )
    else:
        await update.message.reply_text(
            "ℹ️ Нет активных действий для отмены."
        )


async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Авторизация пользователя"""
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Неверный формат!\n"
            "Используйте: /login <username> <password>"
        )
        return
    
    username = context.args[0]
    password = context.args[1]
    
    try:
        logger.info(f"Login attempt for username: {username}")
        
        # Проверяем учетные данные (оборачиваем в sync_to_async)
        user = await sync_to_async(User.objects.filter(username=username).first)()
        
        if not user:
            logger.warning(f"User not found: {username}")
            await update.message.reply_text(
                "❌ Неверное имя пользователя или пароль!"
            )
            return
        
        logger.info(f"User found: {username}, checking password...")
        
        # Проверка пароля также должна быть async
        password_valid = await sync_to_async(user.check_password)(password)
        
        if password_valid:
            # Сохраняем привязку
            telegram_id = update.effective_user.id
            user_mapping[telegram_id] = user.id
            
            # Сохраняем маппинг в файл
            save_user_mapping()
            
            logger.info(f"Password correct! User {username} logged in via Telegram (ID: {telegram_id})")
            
            # Проверяем, является ли пользователь менеджером
            @sync_to_async
            def is_manager():
                return user.groups.filter(name='Менеджеры').exists()
            
            keyboard = get_main_keyboard(await is_manager())
            
            await update.message.reply_text(
                f"✅ Вы успешно авторизованы как {user.username}!\n\n"
                "Выберите действие:",
                reply_markup=keyboard
            )
        else:
            logger.warning(f"Invalid password for username: {username}")
            await update.message.reply_text(
                "❌ Неверное имя пользователя или пароль!"
            )
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при авторизации. Попробуйте позже."
        )


async def my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список задач пользователя"""
    telegram_id = update.effective_user.id
    
    if telegram_id not in user_mapping:
        await update.message.reply_text(
            "❌ Вы не авторизованы!\n"
            "Используйте /login <username> <password>"
        )
        return
    
    try:
        user_id = user_mapping[telegram_id]
        user = await sync_to_async(User.objects.get)(id=user_id)
        
        # Получаем задачи пользователя (только "К выполнению")
        @sync_to_async
        def get_tasks():
            return list(Task.objects.filter(
                assigned_to=user,
                status=Task.STATUS_TODO
            ).select_related('oes_object', 'assigned_to').order_by('-created_at')[:10])
        
        tasks = await get_tasks()
        
        if not tasks:
            await update.message.reply_text(
                "📭 У вас нет активных задач."
            )
            return
        
        # Формируем детальный список задач
        for task in tasks:
            # Получаем данные асинхронно
            @sync_to_async
            def get_task_data(t):
                if t.assigned_to:
                    if t.assigned_to.first_name or t.assigned_to.last_name:
                        assigned_to_name = f"{t.assigned_to.first_name} {t.assigned_to.last_name}".strip()
                    else:
                        assigned_to_name = t.assigned_to.username
                else:
                    assigned_to_name = None
                oes_name = t.oes_name if hasattr(t, 'oes_name') else (t.oes_object.name if t.oes_object else None)
                status_display = t.get_status_display()
                priority_display = t.get_priority_display()
                return assigned_to_name, oes_name, status_display, priority_display
            
            assigned_to_name, oes_name, status_display, priority_display = await get_task_data(task)
            
            status_emoji = {
                'todo': '📝',
                'waiting': '⏳',
                'checking': '🔍',
                'done': '✅'
            }.get(task.status, '❓')
            
            priority_emoji = {
                'critical': '🔴',
                'high': '🟠',
                'medium': '🟡',
                'low': '🟢'
            }.get(task.priority, '⚪')
            
            text = (
                f"{status_emoji} {priority_emoji} *Задача #{task.id}*\n\n"
                f"*Заголовок:* {escape_markdown(task.title)}\n"
                f"*Описание:* {escape_markdown(task.description or 'Не указано')}\n"
                f"*Статус:* {escape_markdown(status_display)}\n"
                f"*Приоритет:* {escape_markdown(priority_display)}\n"
            )
            
            if assigned_to_name:
                text += f"*Исполнитель:* {escape_markdown(assigned_to_name)}\n"
            
            if oes_name:
                text += f"*Актив:* {escape_markdown(oes_name)}\n"
            
            if task.due_date:
                due_date_str = task.due_date.strftime('%d.%m.%Y %H:%M')
                text += f"*Срок:* {due_date_str}\n"
            
            text += f"*ITIL:* {escape_markdown(task.itil_number)}\n"
            
            # Только кнопка закрытия
            keyboard = [
                [
                    InlineKeyboardButton("✅ Закрыть", callback_data=f"close_{task.id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        
    except Exception as e:
        logger.error(f"Error fetching tasks: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при получении списка задач."
        )


async def tasks_for_checking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать задачи на проверке (для менеджеров)"""
    telegram_id = update.effective_user.id
    
    if telegram_id not in user_mapping:
        await update.message.reply_text(
            "❌ Вы не авторизованы!\n"
            "Используйте /login <username> <password>"
        )
        return
    
    try:
        user_id = user_mapping[telegram_id]
        user = await sync_to_async(User.objects.get)(id=user_id)
        
        # Проверяем, является ли пользователь менеджером
        @sync_to_async
        def is_manager():
            return user.groups.filter(name='Менеджеры').exists()
        
        if not await is_manager():
            await update.message.reply_text(
                "❌ У вас нет прав для просмотра задач на проверке."
            )
            return
        
        # Получаем задачи на проверке
        @sync_to_async
        def get_checking_tasks():
            return list(Task.objects.filter(
                status=Task.STATUS_CHECKING
            ).select_related('assigned_to', 'oes_object').order_by('-created_at')[:10])
        
        tasks = await get_checking_tasks()
        
        if not tasks:
            await update.message.reply_text(
                "📭 Нет задач на проверке."
            )
            return
        
        # Формируем детальный список задач
        for task in tasks:
            # Получаем данные асинхронно
            @sync_to_async
            def get_task_data(t):
                if t.assigned_to:
                    if t.assigned_to.first_name or t.assigned_to.last_name:
                        assigned_to_name = f"{t.assigned_to.first_name} {t.assigned_to.last_name}".strip()
                    else:
                        assigned_to_name = t.assigned_to.username
                else:
                    assigned_to_name = None
                oes_name = t.oes_object.name if t.oes_object else None
                status_display = t.get_status_display()
                priority_display = t.get_priority_display()
                return assigned_to_name, oes_name, status_display, priority_display
            
            assigned_to_name, oes_name, status_display, priority_display = await get_task_data(task)
            
            text = (
                f"🔍 *Задача на проверке #{task.id}*\n\n"
                f"*Заголовок:* {escape_markdown(task.title)}\n"
                f"*Описание:* {escape_markdown(task.description or 'Не указано')}\n"
                f"*Статус:* {escape_markdown(status_display)}\n"
                f"*Приоритет:* {escape_markdown(priority_display)}\n"
            )
            
            if assigned_to_name:
                text += f"*Исполнитель:* {escape_markdown(assigned_to_name)}\n"
            
            if oes_name:
                text += f"*Актив:* {escape_markdown(oes_name)}\n"
            
            if task.due_date:
                due_date_str = task.due_date.strftime('%d.%m.%Y %H:%M')
                text += f"*Срок:* {due_date_str}\n"
            
            text += f"*ITIL:* {escape_markdown(task.itil_number)}\n"
            
            # Кнопки для проверки
            keyboard = [
                [
                    InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{task.id}"),
                    InlineKeyboardButton("🔄 Вернуть", callback_data=f"return_{task.id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        
    except Exception as e:
        logger.error(f"Error fetching checking tasks: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при получении списка задач."
        )


async def all_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает все задачи простым списком"""
    try:
        telegram_id = update.effective_user.id
        user_id = user_mapping.get(telegram_id)
        
        if not user_id:
            await update.message.reply_text(
                "❌ Вы не авторизованы! Используйте /start для авторизации."
            )
            return
        
        
        # Получаем все задачи со статусом "к выполнению"
        @sync_to_async
        def get_all_tasks():
            return list(Task.objects.filter(
                status=Task.STATUS_TODO
            ).select_related('assigned_to', 'oes_object').order_by('-priority', 'created_at'))
        
        tasks = await get_all_tasks()
        
        if not tasks:
            await update.message.reply_text(
                "📭 Нет задач в наряде."
            )
            return
        
        # Формируем простой список
        text_lines = ["<b>ВЕСЬ НАРЯД</b>\n"]
        
        for task in tasks:
            # Получаем данные асинхронно
            @sync_to_async
            def get_task_data(t):
                if t.assigned_to:
                    if t.assigned_to.first_name or t.assigned_to.last_name:
                        assignee = f"{t.assigned_to.first_name} {t.assigned_to.last_name}".strip()
                    else:
                        assignee = t.assigned_to.username
                else:
                    assignee = 'Не назначена'
                asset = t.oes_object.name if t.oes_object else 'Без актива'
                return assignee, asset
            
            assignee, asset = await get_task_data(task)
            
            description = task.description if task.description else task.title
            # Экранируем HTML специальные символы
            asset_escaped = asset.replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
            description_escaped = description.replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
            assignee_escaped = assignee.replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
            
            text_lines.append(
                f"<b>{asset_escaped}</b> - {description_escaped} - <i>{assignee_escaped}</i>"
            )
        
        text = '\n'.join(text_lines)
        
        # Разбиваем на части если сообщение слишком длинное
        if len(text) > 4000:
            # Отправляем по частям
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for part in parts:
                await update.message.reply_text(part, parse_mode='HTML')
        else:
            await update.message.reply_text(text, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error fetching all tasks: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при получении наряда."
        )


async def finish_task_closure(query, context: ContextTypes.DEFAULT_TYPE):
    """Завершение закрытия задачи с сохранением отчета и фотографий"""
    try:
        telegram_id = query.from_user.id
        user_id = user_mapping.get(telegram_id)
        
        if not user_id:
            await query.edit_message_text("❌ Вы не авторизованы!")
            return
        
        task_id = context.user_data.get('closing_task_id')
        work_done = context.user_data.get('work_done')
        photos = context.user_data.get('photos', [])
        fault_category_id = context.user_data.get('fault_category_id')
        root_cause = context.user_data.get('root_cause', 'Закрыто через Telegram')
        time_spent = context.user_data.get('time_spent', timedelta(hours=1))
        additional_assignees_ids = context.user_data.get('additional_assignees', [])
        
        if not task_id or not work_done:
            await query.edit_message_text("❌ Данные не найдены. Попробуйте снова.")
            return
        
        user = await sync_to_async(User.objects.get)(id=user_id)
        task = await sync_to_async(Task.objects.get)(id=task_id)
        
        # Создаем отчет о выполнении и закрываем задачу
        @sync_to_async
        def close_task_with_report():
            # Получаем категорию, если указана
            fault_category = None
            if fault_category_id:
                fault_category = FaultCategory.objects.filter(id=fault_category_id).first()
            
            # Проверяем, есть ли уже отчет для этой задачи
            existing_report = TaskCompletionReport.objects.filter(task=task).first()
            
            if existing_report:
                # Обновляем существующий отчет
                existing_report.completed_by = user
                existing_report.work_performed = work_done
                existing_report.fault_category = fault_category
                existing_report.root_cause = root_cause
                existing_report.preventive_measures = 'Не указано'
                existing_report.time_spent = time_spent
                existing_report.save()
                report = existing_report
            else:
                # Создаем новый отчет
                report = TaskCompletionReport.objects.create(
                    task=task,
                    completed_by=user,
                    fault_category=fault_category,
                    work_performed=work_done,
                    root_cause=root_cause,
                    preventive_measures='Не указано',
                    time_spent=time_spent
                )
            
            # Сохраняем дополнительных исполнителей
            if additional_assignees_ids:
                additional_users = User.objects.filter(id__in=additional_assignees_ids)[:3]
                task.additional_assignees.set(additional_users)
            else:
                task.additional_assignees.clear()
            
            # Переводим задачу в статус "Проверка"
            task.status = Task.STATUS_CHECKING
            task.save(update_fields=['status', 'updated_at'])
            return report, fault_category
        
        report, fault_category = await close_task_with_report()
        
        # Загружаем фотографии
        photo_count = 0
        if photos:
            for photo_data in photos:
                try:
                    logger.info(f"Downloading photo {len(context.user_data.get('photos', []))} for task {task_id}")
                    
                    # Скачиваем фото с Telegram серверов
                    file = await context.bot.get_file(photo_data['file_id'])
                    logger.info(f"File downloaded, size: {file.file_size} bytes")
                    
                    # Скачиваем файл как bytearray
                    photo_bytes = await file.download_as_bytearray()
                    logger.info(f"Photo bytes downloaded, length: {len(photo_bytes)}")
                    
                    # Сохраняем в Django
                    @sync_to_async
                    def save_photo():
                        from tasks.models import TaskPhoto
                        from django.core.files.base import ContentFile
                        from django.conf import settings
                        import uuid
                        import os
                        
                        filename = f"telegram_{uuid.uuid4()}.jpg"
                        
                        # Сохраняем файл напрямую
                        task_photos_dir = os.path.join(settings.MEDIA_ROOT, 'task_photos')
                        os.makedirs(task_photos_dir, exist_ok=True)
                        
                        file_path = os.path.join(task_photos_dir, filename)
                        with open(file_path, 'wb') as f:
                            f.write(bytes(photo_bytes))
                        
                        logger.info(f"Photo file written to: {file_path}")
                        logger.info(f"File size: {os.path.getsize(file_path)} bytes")
                        
                        # Создаем запись в БД
                        photo_obj = TaskPhoto.objects.create(
                            task=task,
                            uploaded_by=user,
                            image=f'task_photos/{filename}'
                        )
                        
                        logger.info(f"Photo saved to DB: {photo_obj.image.name}")
                        return photo_obj
                    
                    photo_obj = await save_photo()
                    photo_count += 1
                    logger.info(f"Photo {photo_count} saved successfully for task {task_id}")
                    
                except Exception as e:
                    logger.error(f"Error saving photo: {e}", exc_info=True)
        
        # Отправляем подтверждение
        message = f"✅ Задача #{task.id} закрыта и отправлена на проверку!\n\n"
        message += f"📝 Отчет о выполнении:\n{work_done}\n\n"
        
        if fault_category:
            message += f"🔧 Категория: {fault_category.name}\n"
        
        if root_cause and root_cause != 'Не указано':
            message += f"🔍 Корневая причина: {root_cause}\n"
        
        # Форматируем время
        if time_spent:
            total_seconds = int(time_spent.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            if hours > 0 and minutes > 0:
                time_str = f"{hours} ч {minutes} мин"
            elif hours > 0:
                time_str = f"{hours} ч"
            else:
                time_str = f"{minutes} мин"
            message += f"⏱ Затрачено времени: {time_str}\n"
        
        # Дополнительные исполнители
        if additional_assignees_ids:
            @sync_to_async
            def get_assignee_names():
                return [u.username for u in User.objects.filter(id__in=additional_assignees_ids)]
            
            assignee_names = await get_assignee_names()
            if assignee_names:
                message += f"👥 Доп. исполнители: {', '.join(assignee_names)}\n"
        
        message += "\n"
        
        if photo_count > 0:
            message += f"📸 Прикреплено фотографий: {photo_count}"
        else:
            message += "📸 Фотографии не прикреплены"
        
        await query.edit_message_text(message)
        
        # Отправляем уведомление в группу
        await send_task_closure_to_group(
            context=context,
            task=task,
            user=user,
            work_done=work_done,
            fault_category=fault_category,
            root_cause=root_cause,
            time_spent=time_spent,
            photos=photos
        )
        
        # Очищаем данные
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Error finishing task closure: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка при закрытии задачи.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Обработка выбора дополнительных исполнителей
    if data.startswith('adduser_'):
        user_id = int(data.split('_')[1])
        
        # Инициализируем список, если его нет
        if 'additional_assignees' not in context.user_data:
            context.user_data['additional_assignees'] = []
        
        # Добавляем или убираем пользователя
        if user_id in context.user_data['additional_assignees']:
            context.user_data['additional_assignees'].remove(user_id)
        else:
            if len(context.user_data['additional_assignees']) < 3:
                context.user_data['additional_assignees'].append(user_id)
            else:
                await query.answer("❌ Максимум 3 исполнителя!", show_alert=True)
                return
        
        # Обновляем кнопки
        @sync_to_async
        def get_users_and_names():
            users = list(User.objects.filter(is_active=True).order_by('username')[:20])
            selected_ids = context.user_data.get('additional_assignees', [])
            selected_names = [u.username for u in User.objects.filter(id__in=selected_ids)]
            return users, selected_names
        
        users, selected_names = await get_users_and_names()
        
        keyboard = []
        selected_ids = context.user_data.get('additional_assignees', [])
        
        for user in users:
            prefix = "✅ " if user.id in selected_ids else "👤 "
            keyboard.append([InlineKeyboardButton(
                f"{prefix}{user.username}", 
                callback_data=f"adduser_{user.id}"
            )])
        
        keyboard.append([InlineKeyboardButton("➡️ Продолжить", callback_data="skip_users")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        selected_text = f"\n\nВыбрано: {', '.join(selected_names)}" if selected_names else ""
        
        await query.edit_message_text(
            f"👥 Выберите дополнительных исполнителей (до 3):\n"
            f"Нажмите на пользователя, чтобы добавить/убрать его.{selected_text}",
            reply_markup=reply_markup
        )
        return
    
    # Обработка кнопки пропуска выбора исполнителей
    if data == 'skip_users':
        # Переходим к запросу фотографий
        keyboard = [[InlineKeyboardButton("Пропустить фото", callback_data="skip_photos")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📸 Прикрепите фотографии выполненной работы.\n\n"
            "Отправьте одну или несколько фотографий, затем нажмите 'Завершить' или 'Пропустить'.",
            reply_markup=reply_markup
        )
        return
    
    # Обработка кнопок завершения отчета
    if data == 'skip_photos' or data == 'finish_report':
        await finish_task_closure(query, context)
        return
    
    # Обработка выбора категории неисправности
    if data.startswith('fcat_'):
        if data == 'fcat_skip':
            context.user_data['fault_category_id'] = None
            context.user_data['root_cause'] = 'Не указано'
            # Сразу запрашиваем время, если категория пропущена
            await query.edit_message_text(
                "⏱ Укажите затраченное время в часах\n\n"
                "Примеры форматов:\n"
                "• 1.5 (полтора часа)\n"
                "• 2:30 (два часа 30 минут)\n"
                "• 2 (два часа)"
            )
        else:
            category_id = int(data.split('_')[1])
            context.user_data['fault_category_id'] = category_id
            
            # Запрашиваем корневую причину с возможностью пропуска
            keyboard = [
                [InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_root_cause")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "🔍 Опишите корневую причину неисправности (или нажмите 'Пропустить'):",
                reply_markup=reply_markup
            )
        return
    
    # Обработка пропуска корневой причины
    if data == 'skip_root_cause':
        context.user_data['root_cause'] = 'Не указана'
        # Переходим к следующему шагу - запрос затраченного времени
        await query.edit_message_text(
            "⏱ Укажите затраченное время в часах (например: 1.5 или 2:30):",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_time")]
            ])
        )
        return
    
    # Обработка пропуска времени
    if data == 'skip_time':
        context.user_data['time_spent'] = timedelta(hours=1)  # Значение по умолчанию
        # Переходим к следующему шагу - запрос дополнительных исполнителей
        @sync_to_async
        def get_users():
            return list(User.objects.filter(is_active=True).order_by('username')[:20])
        
        users = await get_users()
        keyboard = []
        for user in users:
            keyboard.append([InlineKeyboardButton(
                f"👤 {user.username}",
                callback_data=f"add_assignee_{user.id}"
            )])
        
        keyboard.append([InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_assignees")])
        keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="finish_assignees")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "👥 Выберите дополнительных исполнителей (необязательно):",
            reply_markup=reply_markup
        )
        return
    
    # Обработка пропуска дополнительных исполнителей
    if data == 'skip_assignees':
        context.user_data['additional_assignees'] = []
        await finish_task_closure(query, context)
        return
    
    # Обработка завершения выбора дополнительных исполнителей
    if data == 'finish_assignees':
        await finish_task_closure(query, context)
        return
    
    action, task_id = data.split('_', 1)
    task_id = int(task_id)
    
    try:
        # Получаем задачу
        @sync_to_async
        def get_task():
            return Task.objects.select_related('assigned_to', 'oes_object').get(id=task_id)
        
        task = await get_task()
        
        if action == 'close':
            # Показать форму закрытия задачи
            await query.edit_message_text(
                f"📝 *Закрытие задачи #{task.id}*\n\n"
                f"{escape_markdown(task.title)}\n\n"
                f"Отправьте описание выполненной работы:",
                parse_mode='Markdown'
            )
            # Сохраняем ID задачи для следующего сообщения
            context.user_data['closing_task_id'] = task_id
        
        elif action == 'approve':
            # Подтвердить выполнение (для менеджеров)
            @sync_to_async
            def approve_task():
                task.status = Task.STATUS_DONE
                task.closed_at = timezone.now()
                task.save(update_fields=['status', 'closed_at', 'updated_at'])
            
            await approve_task()
            await query.edit_message_text(
                f"✅ Задача #{task.id} подтверждена и переведена в статус 'Выполнено'!"
            )
        
        elif action == 'return':
            # Вернуть в работу (для менеджеров)
            @sync_to_async
            def return_task():
                task.status = Task.STATUS_TODO
                task.closed_at = None  # Очищаем дату закрытия при возврате
                task.save(update_fields=['status', 'closed_at', 'updated_at'])
            
            await return_task()
            await query.edit_message_text(
                f"🔄 Задача #{task.id} возвращена в работу."
            )
        
    except Task.DoesNotExist:
        await query.edit_message_text("❌ Задача не найдена.")
    except Exception as e:
        logger.error(f"Button callback error: {e}", exc_info=True)
        await query.edit_message_text("❌ Произошла ошибка.")


async def handle_text_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых кнопок меню"""
    # Проверяем, что сообщение существует
    if not update.message or not update.message.text:
        return
    
    text = update.message.text
    
    if text == "📋 Мои задачи":
        await my_tasks(update, context)
    elif text == "🔍 Задачи на проверке":
        await tasks_for_checking(update, context)
    elif text == "📄 Весь наряд":
        await all_tasks(update, context)
    elif text == "ℹ️ Помощь":
        await help_command(update, context)
    else:
        # Обработка других текстовых сообщений (закрытие задач)
        await handle_message(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений (для закрытия задач)"""
    
    # Проверяем, что сообщение существует
    if not update.message or not update.message.text:
        logger.warning(f"handle_message called without message or text: update={update}")
        return
    
    logger.debug(f"handle_message: user_id={update.effective_user.id}, text={update.message.text[:50]}, user_data_keys={list(context.user_data.keys())}")
    
    # Этап 1: Получение описания работы
    if 'closing_task_id' in context.user_data and 'work_done' not in context.user_data:
        try:
            work_done = update.message.text
            
            # Сохраняем описание работы
            context.user_data['work_done'] = work_done
            
            logger.info(f"User {update.effective_user.id} entered work_done for task {context.user_data.get('closing_task_id')}")
            
            # Запрашиваем категорию неисправности
            @sync_to_async
            def get_fault_categories():
                try:
                    return list(FaultCategory.objects.filter(is_active=True).order_by('sort_order', 'name'))
                except Exception as e:
                    logger.error(f"Error fetching fault categories: {e}", exc_info=True)
                    return []
            
            categories = await get_fault_categories()
            logger.info(f"Retrieved {len(categories)} fault categories")
            
            if categories:
                # Создаем кнопки для категорий (по 2 в ряд)
                keyboard = []
                row = []
                for i, cat in enumerate(categories):
                    try:
                        row.append(InlineKeyboardButton(cat.name, callback_data=f"fcat_{cat.id}"))
                        if len(row) == 2 or i == len(categories) - 1:
                            keyboard.append(row)
                            row = []
                    except Exception as e:
                        logger.error(f"Error creating button for category {cat.id}: {e}", exc_info=True)
                        continue
                
                # Добавляем кнопку "Не указывать"
                keyboard.append([InlineKeyboardButton("❌ Не указывать", callback_data="fcat_skip")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    "🔧 Выберите категорию неисправности:",
                    reply_markup=reply_markup
                )
                logger.info(f"Sent category selection menu to user {update.effective_user.id}")
            else:
                # Если категорий нет, пропускаем этот шаг
                context.user_data['fault_category_id'] = None
                await update.message.reply_text(
                    "🔍 Опишите корневую причину неисправности:"
                )
                logger.info(f"No categories found, skipping to root cause for user {update.effective_user.id}")
        except Exception as e:
            logger.error(f"Error in handle_message stage 1 (work_done): {e}", exc_info=True)
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке описания работы. Попробуйте закрыть задачу заново."
            )
        return
    
    # Этап 2: Получение корневой причины (после выбора категории)
    if 'closing_task_id' in context.user_data and 'work_done' in context.user_data and 'fault_category_id' in context.user_data and 'root_cause' not in context.user_data:
        root_cause = update.message.text
        
        # Сохраняем корневую причину
        context.user_data['root_cause'] = root_cause
        
        # Запрашиваем затраченное время
        await update.message.reply_text(
            "⏱ Укажите затраченное время в часах\n\n"
            "Примеры форматов:\n"
            "• 1.5 (полтора часа)\n"
            "• 2:30 (два часа 30 минут)\n"
            "• 2 (два часа)"
        )
        return
    
    # Этап 3: Получение затраченного времени (после корневой причины)
    if 'closing_task_id' in context.user_data and 'work_done' in context.user_data and 'fault_category_id' in context.user_data and 'root_cause' in context.user_data and 'time_spent' not in context.user_data:
        time_text = update.message.text.strip()
        
        # Парсим время
        time_spent = None
        try:
            # Формат: "1.5" или "1,5" (часы с десятичной дробью)
            if '.' in time_text or ',' in time_text:
                hours = float(time_text.replace(',', '.'))
                time_spent = timedelta(hours=hours)
            # Формат: "1:30" (часы:минуты)
            elif ':' in time_text:
                parts = time_text.split(':')
                hours = int(parts[0])
                minutes = int(parts[1])
                time_spent = timedelta(hours=hours, minutes=minutes)
            # Формат: "2" (только часы)
            else:
                hours = float(time_text)
                time_spent = timedelta(hours=hours)
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Неверный формат времени!\n\n"
                "Используйте формат: 1.5 или 2:30 или 2\n"
                "Попробуйте снова:"
            )
            return
        
        # Сохраняем время
        context.user_data['time_spent'] = time_spent
        
        # Запрашиваем дополнительных исполнителей
        @sync_to_async
        def get_users():
            return list(User.objects.filter(is_active=True).order_by('username')[:20])
        
        users = await get_users()
        
        # Создаем кнопки для выбора исполнителей
        keyboard = []
        for user in users:
            keyboard.append([InlineKeyboardButton(
                f"👤 {user.username}", 
                callback_data=f"adduser_{user.id}"
            )])
        
        # Добавляем кнопки управления
        keyboard.append([InlineKeyboardButton("✅ Продолжить без доп. исполнителей", callback_data="skip_users")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "👥 Выберите дополнительных исполнителей (до 3):\n\n"
            "Нажмите на пользователя, чтобы добавить/убрать его.\n"
            "Затем нажмите 'Продолжить'.",
            reply_markup=reply_markup
        )
        return
    
    # Если пользователь отправил текст после выбора исполнителей - игнорируем
    if 'closing_task_id' in context.user_data and 'time_spent' in context.user_data and 'additional_assignees' in context.user_data:
        await update.message.reply_text(
            "📸 Отправьте фотографии или нажмите 'Пропустить фото'."
        )
        return


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик фотографий"""
    if 'closing_task_id' not in context.user_data or 'time_spent' not in context.user_data:
        return
    
    try:
        # Инициализируем список фотографий, если его еще нет
        if 'photos' not in context.user_data:
            context.user_data['photos'] = []
        
        # Получаем файл фотографии
        photo = update.message.photo[-1]  # Берем самое большое разрешение
        photo_file = await photo.get_file()
        
        # Сохраняем информацию о фото
        context.user_data['photos'].append({
            'file_id': photo.file_id,
            'file_path': photo_file.file_path
        })
        
        photo_count = len(context.user_data['photos'])
        
        # Показываем кнопку для завершения
        keyboard = [[InlineKeyboardButton("✅ Завершить отчет", callback_data="finish_report")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ Фото {photo_count} добавлено!\n\n"
            f"Отправьте еще фото или нажмите 'Завершить'.",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error handling photo: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при загрузке фото.")


def main():
    """Запуск бота"""
    # Загружаем маппинг пользователей
    load_user_mapping()
    
    # Получаем токен из переменной окружения
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    # Создаем приложение
    application = Application.builder().token(token).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("tasks", my_tasks))
    application.add_handler(CommandHandler("checking", tasks_for_checking))
    application.add_handler(CommandHandler("cancel", cancel_command))
    
    # Регистрируем обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Регистрируем обработчик фотографий
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Регистрируем обработчик текстовых кнопок и сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_buttons))
    
    # Запускаем бота
    logger.info("Bot started")
    application.run_polling()


if __name__ == '__main__':
    main()
