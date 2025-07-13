import logging
import asyncio
from uuid import uuid4
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
ADMIN_GROUP_ID = -4908403310  # Замените на ваш ID группы поддержки
BOT_TOKEN = '7960897434:AAEPGs7R10CrWiYDCQOFI0wDEC0ytWkmYv8'  # Вставьте сюда токен вашего бота

# Глобальный словарь для связи ticket_id и user_chat_id
ticket_user_map = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("ЭДО", callback_data="edo"),
         InlineKeyboardButton("Счета", callback_data="scheta")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Привет! Выберите категорию:', reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "edo":
        keyboard = [
            [InlineKeyboardButton("УТЛ", callback_data="utl"),
             InlineKeyboardButton("Логистика", callback_data="logistika")],
            [InlineKeyboardButton("МПИ", callback_data="mpi"),
             InlineKeyboardButton("ФФ", callback_data="ff")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Выберите подраздел:', reply_markup=reply_markup)

    elif data in ["utl", "logistika", "mpi", "ff"]:
        category_map = {
            "utl": "УТЛ",
            "logistika": "Логистика",
            "mpi": "МПИ",
            "ff": "ФФ"
        }
        category_name = category_map[data]
        keyboard = [
            [InlineKeyboardButton("Отправить документы", callback_data=f"{data}_send_docs"),
             InlineKeyboardButton("Принять документы", callback_data=f"{data}_receive_docs")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Ваш выбор: {category_name}. Выберите функцию:", reply_markup=reply_markup)

    elif "_send_docs" in data or "_receive_docs" in data:
        parts = data.split('_')
        category_key = parts[0]
        action_type = parts[1]

        # Генерируем уникальный ID заявки
        unique_id = str(uuid4())

        # Сохраняем связь ticket_id и chat_id пользователя
        user_chat_id = update.effective_user.id
        ticket_user_map[unique_id] = user_chat_id

        # Сохраняем данные в user_data для дальнейшего использования
        context.user_data['unique_id'] = unique_id
        context.user_data['category'] = category_key
        context.user_data['action'] = 'Отправить документы' if action_type == 'send' else 'Принять документы'

        await query.answer()
        await query.edit_message_text(
            f'''Спасибо за ваш выбор!
🆔 Заявка ID: {unique_id}
👤 Пользователь: {update.effective_user.full_name} (@{update.effective_user.username or 'Нет username'}, ID: {update.effective_user.id})
📂 Категория: {category_key}
📂 Функция: {context.user_data['action']}

Теперь пришлите описание проблемы и прикрепите файлы (если нужно).'''
        )
    else:
        await query.edit_message_text("Пожалуйста, выберите ещё раз.")

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обработка текста или файлов после выбора функции
    description = update.message.text or ''
    
    # Получение файлов (если есть)
    file_ids = []

    if update.message.photo:
        largest_photo = update.message.photo[-1]
        file_ids.append(largest_photo.file_id)

    if update.message.document:
        file_ids.append(update.message.document.file_id)

    files_attached = len(file_ids) > 0

    # Формируем сообщение для админов
    unique_id = context.user_data.get('unique_id', 'Не определен')
    category = context.user_data.get('category', 'Не указана')
    action_type = context.user_data.get('action', 'Не указана')

    user_full_name = update.effective_user.full_name
    username_or_none = update.effective_user.username or 'Нет username'

    message_text = (
        f"<b>Новое обращение</b>\n"
        f"<b>🆔 Заявка ID:</b> {unique_id}\n"
        f"<b>👤 Пользователь:</b> {user_full_name} (@{username_or_none}, ID: {update.effective_user.id})\n"
        f"<b>📂 Категория:</b> {category}\n"
        f"<b>📂 Функция:</b> {action_type}\n"
        f"<b>💬 Заявка:</b>\n{description}"
    )

    if not files_attached:
        message_text += "\n<b>🖼️ Скриншот:</b> не предоставлен"

    try:
        # Отправляем сообщение админу/группе поддержки
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=message_text,
            parse_mode='HTML'
        )

        # Отправляем файлы, если есть
        if files_attached:
            media_group = [InputMediaPhoto(media=fid) for fid in file_ids]
            await context.bot.send_media_group(chat_id=ADMIN_GROUP_ID, media=media_group)

        # Подтверждение пользователю
        await update.message.reply_text(
            'Ваш запрос успешно отправлен в бухгалтерию.\nМы свяжемся с вами как можно скорее!\nСпасибо за терпение 🙌'
        )
        
    except Exception as e:
         logger.error(f"Ошибка при отправке обращения: {e}")
         await update.message.reply_text('Возникла ошибка при обработке вашего обращения.')

async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Команда /reply <ID>
    
    args = context.args  # аргументы после команды
    
    if len(args) < 2:
       await update.message.reply_text('Используйте команду /reply <ID> <ваш ответ>')
       return
    
    ticket_id_input = args[0]
    
    response_text = ' '.join(args[1:])
    
    user_chat_id = ticket_user_map.get(ticket_id_input)
    
    if not user_chat_id:
       await update.message.reply_text('Не удалось найти пользователя с таким ID.')
       return
    
    try:
       await context.bot.send_message(
           chat_id=user_chat_id,
           text=f'📌 Ответ службы поддержки:\n\n{response_text}'
       )
       await update.message.reply_text('Ответ отправлен пользователю.')
    except Exception as e:
       logger.error(f"Ошибка при отправке ответа пользователю: {e}")
       await update.message.reply_text('Не удалось отправить ответ пользователю.')

def main():
   application = ApplicationBuilder().token(BOT_TOKEN).build()

   application.add_handler(CommandHandler("start", start))
   application.add_handler(CallbackQueryHandler(button_handler))
   application.add_handler(CommandHandler("reply", reply_command))
   
   # Обработка сообщений (текст и файлы)
   application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_user_message))
   application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_user_message))
   
   application.run_polling()

if __name__ == '__main__':
   main()