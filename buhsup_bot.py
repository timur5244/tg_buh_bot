import logging
from uuid import uuid4
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# Логирование ошибок и сообщений
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

ADMIN_GROUP_ID = -4908403310 # Здесь вставьте id группы поддержки
BOT_TOKEN = '7960897434:AAEPGs7R10CrWiYDCQOFI0wDEC0ytWkmYv8'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("ЭДО", callback_data="edo"), InlineKeyboardButton("Счета", callback_data="scheta")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Привет! Выберите категорию:', reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "edo":
        keyboard = [
            [InlineKeyboardButton("УТЛ", callback_data="utl"),
             InlineKeyboardButton("Логистика", callback_data="logistika"),
             InlineKeyboardButton("МПИ", callback_data="mpi"),
             InlineKeyboardButton("ФФ", callback_data="ff")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="Выберите подраздел:", reply_markup=reply_markup)
    elif query.data in ["utl", "logistika", "mpi", "ff"]:
        category = {"utl": "УТЛ", "logistika": "Логистика", "mpi": "МПИ", "ff": "ФФ"}.get(query.data)
        keyboard = [
            [InlineKeyboardButton("Отправить документы", callback_data=f"{category}_send_docs"),
             InlineKeyboardButton("Принять документы", callback_data=f"{category}_receive_docs")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Ваш выбор: {category}. Выберите функцию:", reply_markup=reply_markup)
    else:
        await query.edit_message_text(f"Пожалуйста, выберите ещё раз.")

async def receive_documents_or_send_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split('_')
    category = data[0]
    function = {'send_docs': 'Отправить документы', 'receive_docs': 'Принять документы'}
    
    user_id = update.effective_user.id
    username = update.effective_user.username or f"User_{user_id}"
    unique_id = str(uuid4())
    
    context.user_data['unique_id'] = unique_id
    context.user_data['category'] = category
    context.user_data['function'] = function[data[1]]
    
    await query.answer()
    await query.edit_message_text(
        text=f'''
Спасибо за ваш выбор!
🆔 Заявка ID: {unique_id}
👤 Пользователь: {username} ({user_id})
📂 Категория: ЭДО => {category}
📂 Функция: {context.user_data["function"]}

Теперь пришлите подробное описание проблемы и прикрепите файлы (если нужно).
''',
        parse_mode='MarkdownV2'
    )

async def handle_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request_description = update.message.text.strip() if update.message.text else ''
    file_ids = []
    media_group = None
    
    for attachment in update.message.media_group_identities():
        if isinstance(attachment, list):
            file_ids.extend([item.file_id for item in attachment])
        else:
            file_ids.append(attachment.file_id)
        
    files_attached = len(file_ids) > 0
    
    message_to_admins = (
        f'<b>Новое обращение\n'
        f'🆔 Заявка ID:</b> {context.user_data["unique_id"]}\n'
        f'<b>👤 Пользователь:</b> {update.effective_user.full_name} (@{update.effective_user.username}, ID: {update.effective_user.id})\n'
        f'<b>📂 Категория:</b> ЭДО => {context.user_data["category"]}\n'
        f'<b>📂 Функция:</b> {context.user_data["function"]}\n'
        f'<b>💬 Заявка:</b>\n{request_description}'
    )
    
    if not files_attached:
        message_to_admins += '\n<b>🖼️ Скриншот:</b> не предоставлен'
    else:
        message_to_admins += '\n<b>🖼️ Файлы предоставлены.</b>'
    
    try:
        admin_reply = await context.bot.send_message(chat_id=ADMIN_GROUP_ID,
                                                    text=message_to_admins,
                                                    parse_mode='HTML')
        
        if files_attached:
            await context.bot.send_media_group(chat_id=ADMIN_GROUP_ID,
                                              media=[InputMediaPhoto(media=file_id) for file_id in file_ids])
            
        await update.message.reply_text(
            '''
Ваш запрос успешно отправлен в службу технической поддержки.\nМы свяжемся с вами как можно скорее!\nСпасибо за терпение 🙌
''',
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        logger.error(e)
        await update.message.reply_text('Возникла ошибка при обработке вашего обращения.')

async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split()
    command = parts.pop(0)[len('/reply'):]
    ticket_id = command.strip()
    response = ' '.join(parts)
    
    original_ticket_message = await context.bot.forward_message(chat_id=update.effective_chat.id,
                                                               from_chat_id=ADMIN_GROUP_ID,
                                                               message_id=update.message.reply_to_message.message_id)
    
    await context.bot.send_message(chat_id=original_ticket_message.forward_from.id,
                                   text=f'''📌 Ответ службы поддержки:\n\n{response}''',
                                   parse_mode='MarkdownV2')

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND | filters.ATTACHMENT, receive_documents_or_send_docs))
    application.add_handler(MessageHandler((filters.TEXT | filters.ATTACHMENT), handle_request))
    application.add_handler(MessageHandler(filters.REPLY & filters.Regex(r'^/reply'), reply_to_user))

    application.run_polling()

if __name__ == '__main__':
    main()