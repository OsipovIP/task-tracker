"""
Telegram бот для Task Tracker
Позволяет просматривать и закрывать задачи через Telegram
"""

import os
import sys
import django
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка Django
sys.path.insert(0, '/usr/src/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_tracker.settings')
django.setup()

from django.contrib.auth import get_user_model
from tasks.models import Task, TaskComment, TaskCompletionReport

User = get_user_model()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Хранилище данных пользователей (telegram_id -> user_id)
user_mapping = {}


# --- КОМАНДЫ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "👋 Добро пожаловать в Task Tracker Bot!\n\n"
        "Для начала работы привяжите свой аккаунт:\n"
        "/login <username> <password>\n\n"
        "Доступные команды:\n"
        "/tasks - Мои задачи\n"
        "/checking - Задачи на проверке (для менеджеров)\n"
        "/help - Помощь"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "📖 Доступные команды:\n\n"
        "/login <username> <password> - Авторизация\n"
        "/tasks - Список моих задач\n"
        "/checking - Задачи на проверке\n"
        "/help - Эта справка\n\n"
        "Для работы с задачей нажмите на нее в списке."
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
        # Проверяем учетные данные
        from django.contrib.auth import authenticate
        user = authenticate(username=username, password=password)
        
        if user is not None:
            # Сохраняем привязку
            telegram_id = update.effective_user.id
            user_mapping[telegram_id] = user.id
            
            await update.message.reply_text(
                f"✅ Вы успешно авторизованы как {user.username}!\n\n"
                "Используйте /tasks для просмотра задач."
            )
            logger.info(f"User {username} logged in via Telegram (ID: {telegram_id})")
        else:
            await update.message.reply_text(
                "❌ Неверное имя пользователя или пароль!"
            )
    except Exception as e:
        logger.error(f"Login error: {e}")
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
        user = User.objects.get(id=user_id)
        
        # Получаем задачи пользователя (кроме выполненных)
        tasks = Task.objects.filter(
            assigned_to=user
        ).exclude(
            status=Task.STATUS_DONE
        ).order_by('-created_at')[:10]
        
        if not tasks:
            await update.message.reply_text(
                "📭 У вас нет активных задач."
            )
            return
        
        # Формируем список задач с кнопками
        for task in tasks:
            status_emoji = {
                'todo': '📝',
                'in_progress': '⚙️',
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
                f"{status_emoji} {priority_emoji} *Задача #{task.id}*\n"
                f"📋 {task.title}\n"
                f"📊 Статус: {task.get_status_display()}\n"
                f"⚡ Приоритет: {task.get_priority_display()}\n"
            )
            
            if task.oes_object:
                text += f"🔧 Актив: {task.oes_object.name}\n"
            
            if task.due_date:
                due_date_str = task.due_date.strftime('%d.%m.%Y %H:%M')
                text += f"⏰ Срок: {due_date_str}\n"
            
            # Кнопки для задачи
            keyboard = [
                [
                    InlineKeyboardButton("👁️ Подробнее", callback_data=f"detail_{task.id}"),
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
        logger.error(f"Error fetching tasks: {e}")
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
        user = User.objects.get(id=user_id)
        
        # Проверяем, является ли пользователь менеджером
        if not user.groups.filter(name='Менеджеры').exists():
            await update.message.reply_text(
                "❌ У вас нет прав для просмотра задач на проверке."
            )
            return
        
        # Получаем задачи на проверке
        tasks = Task.objects.filter(
            status=Task.STATUS_CHECKING
        ).order_by('-created_at')[:10]
        
        if not tasks:
            await update.message.reply_text(
                "📭 Нет задач на проверке."
            )
            return
        
        # Формируем список задач с кнопками
        for task in tasks:
            text = (
                f"🔍 *Задача на проверке #{task.id}*\n"
                f"📋 {task.title}\n"
                f"👤 Исполнитель: {task.assigned_to.username if task.assigned_to else 'Не назначен'}\n"
            )
            
            if task.oes_object:
                text += f"🔧 Актив: {task.oes_object.name}\n"
            
            # Кнопки для проверки
            keyboard = [
                [
                    InlineKeyboardButton("👁️ Подробнее", callback_data=f"detail_{task.id}"),
                ],
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
        logger.error(f"Error fetching checking tasks: {e}")
        await update.message.reply_text(
            "❌ Ошибка при получении списка задач."
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    action, task_id = data.split('_', 1)
    task_id = int(task_id)
    
    try:
        task = Task.objects.get(id=task_id)
        
        if action == 'detail':
            # Показать детальную информацию
            text = (
                f"📋 *Задача #{task.id}*\n\n"
                f"*Заголовок:* {task.title}\n"
                f"*Описание:* {task.description or 'Не указано'}\n"
                f"*Статус:* {task.get_status_display()}\n"
                f"*Приоритет:* {task.get_priority_display()}\n"
            )
            
            if task.assigned_to:
                text += f"*Исполнитель:* {task.assigned_to.username}\n"
            
            if task.oes_object:
                text += f"*Актив:* {task.oes_object.name}\n"
            
            if task.due_date:
                due_date_str = task.due_date.strftime('%d.%m.%Y %H:%M')
                text += f"*Срок:* {due_date_str}\n"
            
            await query.edit_message_text(text, parse_mode='Markdown')
        
        elif action == 'close':
            # Показать форму закрытия задачи
            await query.edit_message_text(
                f"📝 *Закрытие задачи #{task.id}*\n\n"
                f"{task.title}\n\n"
                f"Отправьте описание выполненной работы:",
                parse_mode='Markdown'
            )
            # Сохраняем ID задачи для следующего сообщения
            context.user_data['closing_task_id'] = task_id
        
        elif action == 'approve':
            # Подтвердить выполнение (для менеджеров)
            task.status = Task.STATUS_DONE
            task.save()
            await query.edit_message_text(
                f"✅ Задача #{task.id} подтверждена и переведена в статус 'Выполнено'!"
            )
        
        elif action == 'return':
            # Вернуть в работу (для менеджеров)
            task.status = Task.STATUS_IN_PROGRESS
            task.save()
            await query.edit_message_text(
                f"🔄 Задача #{task.id} возвращена в работу."
            )
        
    except Task.DoesNotExist:
        await query.edit_message_text("❌ Задача не найдена.")
    except Exception as e:
        logger.error(f"Button callback error: {e}")
        await query.edit_message_text("❌ Произошла ошибка.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений (для закрытия задач)"""
    if 'closing_task_id' in context.user_data:
        task_id = context.user_data['closing_task_id']
        work_done = update.message.text
        
        try:
            telegram_id = update.effective_user.id
            user_id = user_mapping.get(telegram_id)
            
            if not user_id:
                await update.message.reply_text("❌ Вы не авторизованы!")
                return
            
            user = User.objects.get(id=user_id)
            task = Task.objects.get(id=task_id)
            
            # Создаем отчет о выполнении
            report = TaskCompletionReport.objects.create(
                task=task,
                completed_by=user,
                work_done=work_done,
                failure_category='other',
                root_cause='Закрыто через Telegram',
                preventive_measures='Не указано',
                time_spent=0
            )
            
            # Переводим задачу в статус "Проверка"
            task.status = Task.STATUS_CHECKING
            task.save()
            
            await update.message.reply_text(
                f"✅ Задача #{task.id} закрыта и отправлена на проверку!\n\n"
                f"Отчет о выполнении:\n{work_done}"
            )
            
            # Очищаем данные
            del context.user_data['closing_task_id']
            
        except Exception as e:
            logger.error(f"Error closing task: {e}")
            await update.message.reply_text("❌ Ошибка при закрытии задачи.")


def main():
    """Запуск бота"""
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
    
    # Регистрируем обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Регистрируем обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    logger.info("Bot started")
    application.run_polling()


if __name__ == '__main__':
    main()
