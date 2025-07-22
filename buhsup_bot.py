import logging
import asyncio
from uuid import uuid4
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaDocument
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
ADMIN_GROUP_ID = -4868585948  # Замените на ваш ID группы поддержки
BOT_TOKEN = '7960897434:AAEPGs7R10CrWiYDCQOFI0wDEC0ytWkmYv8'  # Вставьте сюда токен вашего бота

# Глобальные хранилища данных
ticket_user_map = {}  # {ticket_id: user_chat_id}
user_tickets = {}     # {user_id: {ticket_id: ticket_data}}
active_tickets = {}   # {ticket_id: ticket_data}
user_descriptions = {} # {user_id: {'text': description, 'files': []}}

class TicketStatus:
    ACTIVE = "active"
    CLOSED = "closed"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("ЭДО", callback_data="edo"),
         InlineKeyboardButton("Счета", callback_data="scheta")],
        [InlineKeyboardButton("Мои заявки", callback_data="my_tickets")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text('Привет! Выберите категорию:', reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text('Привет! Выберите категорию:', reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "edo":
        keyboard = [
            [InlineKeyboardButton("УТЛ", callback_data="utl"),
             InlineKeyboardButton("Логистика", callback_data="logistika")],
            [InlineKeyboardButton("МПИ", callback_data="mpi"),
             InlineKeyboardButton("ФФ", callback_data="ff")],
            [InlineKeyboardButton("Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Выберите подраздел:', reply_markup=reply_markup)

    elif data == "scheta":
        keyboard = [
            [InlineKeyboardButton("УТЛ", callback_data="scheta_utl"),
             InlineKeyboardButton("Логистика", callback_data="scheta_logistika")],
            [InlineKeyboardButton("МПИ", callback_data="scheta_mpi"),
             InlineKeyboardButton("ФФ", callback_data="scheta_ff")],
            [InlineKeyboardButton("Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Выберите категорию для работы со счетами:', reply_markup=reply_markup)

    elif data.startswith("scheta_"):
        category_key = data.replace("scheta_", "")
        category_map = {
            "utl": "УТЛ",
            "logistika": "Логистика",
            "mpi": "МПИ",
            "ff": "ФФ"
        }
        category_name = category_map[category_key]
        keyboard = [
            [InlineKeyboardButton("Поставить в график платежей", callback_data=f"create_invoice_{category_key}"),
             InlineKeyboardButton("Счет согласован\nСрочная оплата", callback_data=f"check_invoice_{category_key}")],
            [InlineKeyboardButton("Назад", callback_data="scheta")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Категория: {category_name}. Выберите действие:", reply_markup=reply_markup)

    elif data == "my_tickets":
        await show_user_tickets(query, update.effective_user.id)

    elif data in ["back_to_main", "back"]:
        await start(update, context)

    elif data.startswith("close_ticket_"):
        ticket_id = data.replace("close_ticket_", "")
        await close_ticket(ticket_id, query)

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
             InlineKeyboardButton("Принять документы", callback_data=f"{data}_receive_docs")],
            [InlineKeyboardButton("Назад", callback_data="back_to_edo")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Ваш выбор: {category_name}. Выберите функцию:", reply_markup=reply_markup)

    elif data == "back_to_edo":
        keyboard = [
            [InlineKeyboardButton("УТЛ", callback_data="utl"),
             InlineKeyboardButton("Логистика", callback_data="logistika")],
            [InlineKeyboardButton("МПИ", callback_data="mpi"),
             InlineKeyboardButton("ФФ", callback_data="ff")],
            [InlineKeyboardButton("Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Выберите подраздел:', reply_markup=reply_markup)

    elif "_send_docs" in data or "_receive_docs" in data or "create_invoice_" in data or "check_invoice_" in data:
        if "_send_docs" in data or "_receive_docs" in data:
            parts = data.split('_')
            category_key = parts[0]
            action_type = parts[1]
            action_text = 'Отправить документы' if action_type == 'send' else 'Принять документы'
            ticket_type = 'ЭДО'
        else:
            parts = data.split('_')
            category_key = parts[2]
            action_type = parts[0] + '_' + parts[1]
            action_text = 'Поставить в график платежей' if parts[0] == 'create' else 'Счет согласован'
            ticket_type = 'Счета'

        # Генерируем уникальный ID заявки
        unique_id = str(uuid4())
        user_id = update.effective_user.id

        # Сохраняем связь ticket_id и chat_id пользователя
        ticket_user_map[unique_id] = user_id

        # Создаем запись о заявке
        ticket_data = {
            "id": unique_id,
            "user_id": user_id,
            "user_name": update.effective_user.full_name,
            "username": update.effective_user.username or 'Нет username',
            "category": category_key,
            "action": action_text,
            "type": ticket_type,
            "status": TicketStatus.ACTIVE,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "closed_at": None,
            "description": None,
            "files": []
        }

        # Сохраняем в глобальных хранилищах
        active_tickets[unique_id] = ticket_data
        if user_id not in user_tickets:
            user_tickets[user_id] = {}
        user_tickets[user_id][unique_id] = ticket_data

        # Инициализируем хранилище для описания и файлов
        user_descriptions[user_id] = {
            'ticket_id': unique_id,
            'text': None,
            'files': []
        }

        # Сохраняем данные в user_data для дальнейшего использования
        context.user_data['unique_id'] = unique_id
        context.user_data['category'] = category_key
        context.user_data['action'] = action_text
        context.user_data['ticket_type'] = ticket_type

        await query.answer()
        await query.edit_message_text(
            f'''Спасибо за ваш выбор!
🆔 Заявка ID: {unique_id}
👤 Пользователь: {update.effective_user.full_name} (@{update.effective_user.username or 'Нет username'}, ID: {update.effective_user.id})
📂 Тип: {ticket_type}
📂 Категория: {category_key}
📂 Функция: {action_text}

Пришлите текстовое описание запроса и/или вложения'''
        )
    else:
        await query.edit_message_text("Пожалуйста, выберите ещё раз.")

async def show_user_tickets(query, user_id):
    if user_id not in user_tickets or not user_tickets[user_id]:
        await query.edit_message_text("У вас нет активных заявок.")
        return

    active_tickets_list = [t for t in user_tickets[user_id].values() if t['status'] == TicketStatus.ACTIVE]
    
    if not active_tickets_list:
        await query.edit_message_text("У вас нет активных заявок.")
        return

    message = "📋 Ваши активные заявки:\n\n"
    for ticket in active_tickets_list:
        message += (
            f"🆔 ID: {ticket['id']}\n"
            f"📂 Тип: {ticket.get('type', 'ЭДО')}\n"
            f"📂 Категория: {ticket['category']}\n"
            f"📌 Действие: {ticket['action']}\n"
            f"📝 Описание: {ticket.get('description', 'нет описания')}\n"
            f"🕒 Создана: {ticket['created_at']}\n"
            f"────────────────────\n"
        )

    await query.edit_message_text(message)

async def close_ticket(ticket_id, query):
    if ticket_id not in active_tickets:
        await query.answer("Заявка не найдена или уже закрыта", show_alert=True)
        return

    ticket = active_tickets[ticket_id]
    ticket['status'] = TicketStatus.CLOSED
    ticket['closed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Уведомляем пользователя
    try:
        await query.bot.send_message(
            chat_id=ticket['user_id'],
            text=f"✅ Ваша заявка {ticket_id} была закрыта.\n\n"
                 f"📂 Тип: {ticket.get('type', 'ЭДО')}\n"
                 f"📂 Категория: {ticket['category']}\n"
                 f"📌 Действие: {ticket['action']}\n"
                 f"🕒 Закрыта: {ticket['closed_at']}"
        )
    except Exception as e:
        logger.error(f"Ошибка при уведомлении пользователя: {e}")

    # Удаляем из активных
    del active_tickets[ticket_id]

    # Обновляем статус в user_tickets
    if ticket['user_id'] in user_tickets and ticket_id in user_tickets[ticket['user_id']]:
        user_tickets[ticket['user_id']][ticket_id]['status'] = TicketStatus.CLOSED
        user_tickets[ticket['user_id']][ticket_id]['closed_at'] = ticket['closed_at']

    await query.answer(f"Заявка {ticket_id} закрыта", show_alert=True)
    await query.message.reply_text(f"Заявка {ticket_id} успешно закрыта.")

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_descriptions:
        # Если пользователь не начал создавать заявку, предлагаем начать
        await start(update, context)
        return

    unique_id = user_descriptions[user_id]['ticket_id']
    ticket_data = active_tickets.get(unique_id)
    
    if not ticket_data:
        await update.message.reply_text('Ошибка: заявка не найдена')
        return

    # Обработка текста (если есть)
    if update.message.text:
        user_descriptions[user_id]['text'] = update.message.text
        ticket_data['description'] = update.message.text
        if user_id in user_tickets and unique_id in user_tickets[user_id]:
            user_tickets[user_id][unique_id]['description'] = update.message.text

    # Обработка вложений (если есть)
    file_id = None
    if update.message.document:
        file_id = update.message.document.file_id
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id  # Берем самое большое фото
    
    if file_id:
        user_descriptions[user_id]['files'].append(file_id)
        ticket_data['files'] = user_descriptions[user_id]['files']
        if user_id in user_tickets and unique_id in user_tickets[user_id]:
            user_tickets[user_id][unique_id]['files'] = user_descriptions[user_id]['files']

    # Если есть хотя бы текст или файлы - отправляем заявку
    if user_descriptions[user_id]['text'] or user_descriptions[user_id]['files']:
        await send_full_ticket_to_admin(update, context, unique_id, user_id)
    else:
        await update.message.reply_text('Пожалуйста, отправьте текстовое описание или вложение')

async def send_full_ticket_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_id: str, user_id: int):
    # Получаем данные заявки
    ticket_data = active_tickets.get(ticket_id)
    if not ticket_data:
        await update.message.reply_text('Ошибка: заявка не найдена')
        return
    
    # Получаем описание и файлы
    description_data = user_descriptions.get(user_id, {})
    description_text = description_data.get('text', 'нет описания')
    files = description_data.get('files', [])
    
    # Формируем сообщение для админов
    message_text = (
        f"<b>Новое обращение</b>\n"
        f"<b>🆔 Заявка ID:</b> {ticket_id}\n"
        f"<b>👤 Пользователь:</b> {ticket_data['user_name']} (@{ticket_data['username']}, ID: {user_id})\n"
        f"<b>📂 Тип:</b> {ticket_data['type']}\n"
        f"<b>📂 Категория:</b> {ticket_data['category']}\n"
        f"<b>📂 Функция:</b> {ticket_data['action']}\n"
        f"<b>💬 Описание:</b>\n{description_text}\n"
        f"<b>📎 Файлы:</b> {len(files)} шт."
    )

    # Добавляем кнопку закрытия заявки для админов
    close_button = InlineKeyboardButton(
        "Закрыть заявку", 
        callback_data=f"close_ticket_{ticket_id}"
    )
    reply_markup = InlineKeyboardMarkup([[close_button]])

    try:
        # Если есть файлы, отправляем их с текстом
        if files:
            media_group = []
            # Первый элемент медиа-группы будет содержать подпись с текстом заявки
            for i, file_id in enumerate(files[:10]):  # Ограничение Telegram - 10 файлов в одной группе
                if i == 0:
                    # Для первого файла добавляем описание
                    if update.message.document:
                        media_group.append(InputMediaDocument(media=file_id, caption=message_text, parse_mode='HTML'))
                    elif update.message.photo:
                        media_group.append(InputMediaPhoto(media=file_id, caption=message_text, parse_mode='HTML'))
                else:
                    # Для остальных файлов без описания
                    if update.message.document:
                        media_group.append(InputMediaDocument(media=file_id))
                    elif update.message.photo:
                        media_group.append(InputMediaPhoto(media=file_id))
            
            # Отправляем медиа-группу
            await context.bot.send_media_group(
                chat_id=ADMIN_GROUP_ID,
                media=media_group
            )
            
            # Отправляем кнопку отдельным сообщением
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=f"🆔 Заявка ID: {ticket_id}",
                reply_markup=reply_markup
            )
        else:
            # Если нет файлов, отправляем только текст с кнопкой
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=message_text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )

        # Подтверждение пользователю
        await update.message.reply_text(
            '✅ Ваш запрос успешно отправлен бухгалтеру.\nМы сообщим когда документы будут готовы!'
        )
        
        # Очищаем временные данные
        if user_id in user_descriptions:
            del user_descriptions[user_id]
        
        # Возвращаем пользователя в начало
        await start(update, context)
        
    except Exception as e:
        logger.error(f"Ошибка при отправке обращения: {e}")
        await update.message.reply_text('⚠️ Возникла ошибка при обработке вашего обращения.')

async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text('Используйте: /reply <ID_заявки> <ваш ответ>')
        return
    
    ticket_id_input = args[0]
    response_text = ' '.join(args[1:])
    
    user_chat_id = ticket_user_map.get(ticket_id_input)
    
    if not user_chat_id:
        await update.message.reply_text('❌ Не найден пользователь с таким ID заявки.')
        return
    
    try:
        await context.bot.send_message(
            chat_id=user_chat_id,
            text=f'📩 Ответ от бухгалтерии:\n\n{response_text}'
        )
        await update.message.reply_text('✅ Ответ успешно отправлен пользователю.')
    except Exception as e:
        logger.error(f"Ошибка при отправке ответа: {e}")
        await update.message.reply_text('❌ Не удалось отправить ответ.')

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CommandHandler("reply", reply_command))
    
    # Обработка текстовых сообщений и вложений
    application.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.Document.ALL, 
        handle_user_message
    ))
    
    application.run_polling()

if __name__ == '__main__':
    main()