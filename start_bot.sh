#!/bin/bash
# Скрипт запуска Telegram бота

echo "Waiting for Django to be ready..."
sleep 10

echo "Starting Telegram bot..."
python /usr/src/app/telegram_bot/bot.py



