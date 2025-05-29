import logging
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import asyncio

API_TOKEN = '8162663853:AAHasVnLHU5bkyWVAHlWZxGXNy2uNn-O58w'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Подключение к базе данных
try:
    conn = psycopg2.connect(dbname="Music service", user="user1", password="12345678", host="localhost")
    cursor = conn.cursor()
    logging.info("Successfully connected to the database.")
except psycopg2.OperationalError as e:
    logging.error(f"Database connection error: {e}")
    conn = None
    cursor = None


# Объявление состояний
class AuthStates(StatesGroup):
    waiting_for_username_login = State()
    waiting_for_password_login = State()
    waiting_for_email_reg = State()
    waiting_for_username_reg = State()
    waiting_for_password_reg = State()


class SearchStates(StatesGroup):
    waiting_for_track_query = State()
    waiting_for_album_query = State()
    waiting_for_artist_query = State()


# --- Основное меню ---
def get_main_menu_markup():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Поиск 🔎", callback_data="main_menu_search")],
        [types.InlineKeyboardButton(text="Моя библиотека 📚", callback_data="main_menu_library")],
        [types.InlineKeyboardButton(text="Добавить ➕", callback_data="main_menu_add")],
        [types.InlineKeyboardButton(text="Аккаунт 👤", callback_data="main_menu_account")]
    ])


def get_search_menu_markup():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Поиск треков", callback_data="search_tracks_opt")],
        [types.InlineKeyboardButton(text="Поиск альбомов", callback_data="search_albums_opt")],
        [types.InlineKeyboardButton(text="Поиск исполнителей", callback_data="search_artists_opt")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu_back")]
    ])


# Хэлпер для проверки авторизации
async def ensure_authenticated(message_or_cq: types.Message | types.CallbackQuery, state: FSMContext):
    if not conn or not cursor:
        msg_target = message_or_cq.message if isinstance(message_or_cq, types.CallbackQuery) else message_or_cq
        await msg_target.reply("❌ Ошибка подключения к базе данных. Действие невозможно.")
        if isinstance(message_or_cq, types.CallbackQuery): await message_or_cq.answer()
        return None

    user_data = await state.get_data()
    if not user_data.get('user_id_db'):
        msg_target = message_or_cq.message if isinstance(message_or_cq, types.CallbackQuery) else message_or_cq
        await msg_target.reply("⚠️ Вы не авторизованы. Пожалуйста, используйте /login или кнопку 'Авторизация'.")
        if isinstance(message_or_cq, types.CallbackQuery): await message_or_cq.answer(
            "Сессия истекла или вы не авторизованы.", show_alert=True)
        return None
    return user_data


@dp.message(Command("start"))
async def send_welcome(message: types.Message, state: FSMContext):
    await state.clear()
    await message.reply("🎵 Добро пожаловать в музыкальный сервис Bot!")
    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Авторизация (Вход)", callback_data="auth_login_start")],
        [types.InlineKeyboardButton(text="Регистрация", callback_data="auth_register_start")]
    ])
    await message.answer(
        f"Привет, {message.from_user.full_name}! Пожалуйста, войдите или зарегистрируйтесь.",
        reply_markup=markup
    )


# Регистрация нового пользователя
@dp.callback_query(lambda c: c.data == 'auth_register_start')
async def process_register_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not conn or not cursor:
        await callback_query.message.answer("❌ Ошибка подключения к базе данных. Регистрация невозможна.")
        await callback_query.answer()
        return
    await callback_query.message.answer("📝 Регистрация нового пользователя.\nПожалуйста, введите ваш email:")
    await state.set_state(AuthStates.waiting_for_email_reg)
    await callback_query.answer()


@dp.message(AuthStates.waiting_for_email_reg)
async def process_email_reg(message: types.Message, state: FSMContext):
    await state.update_data(reg_email=message.text)
    await message.answer("Введите username:")
    await state.set_state(AuthStates.waiting_for_username_reg)


@dp.message(AuthStates.waiting_for_username_reg)
async def process_username_reg(message: types.Message, state: FSMContext):
    await state.update_data(reg_username=message.text)
    await message.answer("Придумайте пароль (макс. 32 символа):")
    await state.set_state(AuthStates.waiting_for_password_reg)


@dp.message(AuthStates.waiting_for_password_reg)
async def process_password_reg(message: types.Message, state: FSMContext):
    if not conn or not cursor:
        await message.reply("❌ Ошибка подключения к базе данных. Регистрация не удалась.")
        await state.clear()
        return
    reg_password = message.text
    if len(reg_password) > 32:
        await message.answer("Пароль слишком длинный. Пожалуйста, введите пароль до 32 символов:")
        return


    user_data_reg = await state.get_data()
    reg_email = user_data_reg.get('reg_email')
    reg_username = user_data_reg.get('reg_username')

    try:
        cursor.execute("SELECT id FROM \"user\" WHERE username = %s OR mail = %s", (reg_username, reg_email))
        if cursor.fetchone():
            await message.reply(
                "ℹ️ Пользователь с таким username или email уже существует. Попробуйте другие данные или /login.")
            await state.clear()
            return

        cursor.execute(
            "INSERT INTO \"user\" (mail, username, password) VALUES (%s, %s, %s) RETURNING id, username",
            (reg_email, reg_username, reg_password)
        )
        new_user_db_id, new_user_db_username = cursor.fetchone()
        conn.commit()
        await message.reply(f"✅ Регистрация прошла успешно, {new_user_db_username}!\n"
                            f"Теперь вы можете войти с помощью /login или кнопки 'Авторизация'.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка регистрации: {e}")
        await message.reply("❌ Ошибка при регистрации. Попробуйте позже.")
    finally:
        await state.clear()


# Вход в аккаунт
@dp.callback_query(lambda c: c.data == 'auth_login_start')
@dp.message(Command("login"))
async def process_login_start(event: types.Message | types.CallbackQuery, state: FSMContext):
    if not conn or not cursor:
        msg_target = event.message if isinstance(event, types.CallbackQuery) else event
        await msg_target.answer("❌ Ошибка подключения к базе данных. Вход невозможен.")
        if isinstance(event, types.CallbackQuery): await event.answer()
        return

    current_message = event.message if isinstance(event, types.CallbackQuery) else event
    await current_message.answer("🔑 Вход в систему.\nПожалуйста, введите ваш username:")
    await state.set_state(AuthStates.waiting_for_username_login)
    if isinstance(event, types.CallbackQuery):
        await event.answer()


@dp.message(AuthStates.waiting_for_username_login)
async def process_username_login(message: types.Message, state: FSMContext):
    await state.update_data(login_username=message.text)
    await message.answer("Теперь введите ваш пароль:")
    await state.set_state(AuthStates.waiting_for_password_login)


@dp.message(AuthStates.waiting_for_password_login)
async def process_password_login(message: types.Message, state: FSMContext):
    if not conn or not cursor:
        await message.reply("❌ Ошибка подключения к базе данных. Вход не удался.")
        await state.clear()
        return

    user_data_login = await state.get_data()
    input_username = user_data_login.get('login_username')
    input_password = message.text

    try:
        cursor.execute(
            "SELECT id, username FROM \"user\" WHERE username = %s AND password = %s",
            (input_username, input_password)
        )
        db_user = cursor.fetchone()

        if db_user:
            user_id_db, username_db = db_user
            await state.update_data(user_id_db=user_id_db, username_db=username_db, authenticated=True)
            await message.answer(f"✅ Авторизация успешна, {username_db}!")
            await message.answer("Главное меню:", reply_markup=get_main_menu_markup())
        else:
            await message.answer("❌ Неверный username или пароль. Попробуйте снова или /register.")
            await state.clear()
    except Exception as e:
        logging.error(f"Ошибка авторизации: {e}")
        await message.reply("❌ Ошибка при авторизации. Попробуйте позже.")
        await state.clear()


# --- Main Menu Handlers ---
@dp.callback_query(lambda c: c.data == 'main_menu_back')
async def handle_main_menu_back(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        await callback_query.message.edit_text("Главное меню:", reply_markup=get_main_menu_markup())
    except Exception as e:
        logging.warning(f"Failed to edit message for main menu back: {e}")
        await callback_query.message.answer("Главное меню:", reply_markup=get_main_menu_markup())
    await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'main_menu_search')
async def handle_menu_search(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    await callback_query.message.edit_text("Меню поиска:", reply_markup=get_search_menu_markup())
    await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'main_menu_library')
async def handle_menu_library(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    library_markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Мои плейлисты", callback_data="library_my_playlists")],
        [types.InlineKeyboardButton(text="Понравившиеся треки", callback_data="library_liked_tracks")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu_back")]
    ])
    await callback_query.message.edit_text("Моя библиотека:", reply_markup=library_markup)
    await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'main_menu_add')
async def handle_menu_add(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    add_markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Добавить трек", callback_data="add_menu_track_cmd")],
        [types.InlineKeyboardButton(text="Создать плейлист", callback_data="add_menu_playlist_cmd")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu_back")]
    ])
    await callback_query.message.edit_text("Что вы хотите добавить?", reply_markup=add_markup)
    await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'main_menu_account')
async def handle_menu_account(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    username_db = user_auth_data.get('username_db', 'N/A')
    account_markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Информация об аккаунте", callback_data="account_info_opt")],
        [types.InlineKeyboardButton(text="Выйти", callback_data="account_logout_opt")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu_back")]
    ])
    await callback_query.message.edit_text(f"Аккаунт: {username_db}", reply_markup=account_markup)
    await callback_query.answer()


# --- Search Sub-Menu and FSM Handlers ---
@dp.callback_query(lambda c: c.data == 'search_tracks_opt')
async def handle_search_tracks_opt(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    await callback_query.message.edit_text("Введите название трека для поиска:")
    await state.set_state(SearchStates.waiting_for_track_query)
    await callback_query.answer()


@dp.message(SearchStates.waiting_for_track_query)
async def process_track_search_query(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        await state.clear()
        return

    query = message.text
    try:
        cursor.execute(
            """SELECT t.id, t.name, al.title as album_name, au.name as author_name
               FROM track t
                        LEFT JOIN album al ON t.album_id = al.id
                        LEFT JOIN author au ON al.author_id = au.id
               WHERE t.name ILIKE %s
                   LIMIT 10""",
            (f'%{query}%',)
        )
        tracks = cursor.fetchall()
        if tracks:
            response_text = "🎶 Найденные треки:\n" + "\n".join(
                [f"ID: {tid}. {name} (Альбом: {album if album else 'N/A'}, Исп: {author if author else 'N/A'})"
                 for tid, name, album, author in tracks]
            )
        else:
            response_text = "❌ Треки с таким названием не найдены."
        await message.answer(response_text)
    except Exception as e:
        logging.error(f"Ошибка поиска треков: {e}")
        await message.answer("❌ Произошла ошибка при поиске треков.")
    finally:
        await state.clear()
        await message.answer("Меню поиска:", reply_markup=get_search_menu_markup())


@dp.callback_query(lambda c: c.data == 'search_albums_opt')
async def handle_search_albums_opt(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    await callback_query.message.edit_text("Введите название альбома для поиска:")
    await state.set_state(SearchStates.waiting_for_album_query)
    await callback_query.answer()


@dp.message(SearchStates.waiting_for_album_query)
async def process_album_search_query(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        await state.clear()
        return

    query = message.text
    try:
        cursor.execute(
            """SELECT al.id, al.title, au.name as author_name, g.name as genre_name
               FROM album al
                        LEFT JOIN author au ON al.author_id = au.id
                        LEFT JOIN genre g ON al.genre_id = g.id
               WHERE al.title ILIKE %s
                   LIMIT 10""",
            (f'%{query}%',)
        )
        albums = cursor.fetchall()
        if albums:
            response_text = "💿 Найденные альбомы:\n" + "\n".join(
                [f"ID: {aid}. {title} (Исполнитель: {author if author else 'N/A'}, Жанр: {genre if genre else 'N/A'})"
                 for aid, title, author, genre in albums]
            )
        else:
            response_text = "❌ Альбомы с таким названием не найдены."
        await message.answer(response_text)
    except Exception as e:
        logging.error(f"Ошибка поиска альбомов: {e}")
        await message.answer("❌ Произошла ошибка при поиске альбомов.")
    finally:
        await state.clear()
        await message.answer("Меню поиска:", reply_markup=get_search_menu_markup())


@dp.callback_query(lambda c: c.data == 'search_artists_opt')
async def handle_search_artists_opt(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    await callback_query.message.edit_text("Введите имя или часть имени исполнителя для поиска:")
    await state.set_state(SearchStates.waiting_for_artist_query)
    await callback_query.answer()


@dp.message(SearchStates.waiting_for_artist_query)
async def process_artist_search_query(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        await state.clear()
        return

    query = message.text
    try:
        cursor.execute(
            """SELECT id, name, auditions, bio
               FROM author
               WHERE name ILIKE %s
                   LIMIT 10""",
        (f'%{query}%',)
        )
        artists = cursor.fetchall()
        if artists:
            response_text = "🎤 Найденные исполнители:\n" + "\n\n".join(
                [f"ID: {aid}. {name}\nПрослушиваний: {auditions if auditions else 0}\nBIO: {bio if bio else 'N/A'}"
                 for aid, name, auditions, bio in artists]
            )
        else:
            response_text = "❌ Исполнители с таким именем не найдены."
        await message.answer(response_text)
    except Exception as e:
        logging.error(f"Ошибка поиска исполнителей: {e}")
        await message.answer("❌ Произошла ошибка при поиске исполнителей.")
    finally:
        await state.clear()
        await message.answer("Меню поиска:", reply_markup=get_search_menu_markup())


# --- Library Sub-menu Handlers ---
@dp.callback_query(lambda c: c.data == 'library_my_playlists')
async def handle_library_my_playlists(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    await list_my_playlists(callback_query.message, state)
    await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'library_liked_tracks')
async def handle_library_liked_tracks(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    user_id_db = user_auth_data.get('user_id_db')
    try:
        cursor.execute("""
                       SELECT t.id, t.name, al.title as album_name, au.name as author_name
                       FROM track t
                                JOIN user_reaction ur ON t.id = ur.track_id
                                JOIN reactions r ON ur.reaction_id = r.id
                                LEFT JOIN album al ON t.album_id = al.id
                                LEFT JOIN author au ON al.author_id = au.id
                       WHERE ur.user_id = %s
                         AND r.type = 'like'
                       ORDER BY t.name LIMIT 20
                       """,
                       (user_id_db,))
        tracks = cursor.fetchall()
        if tracks:
            text = "👍 Понравившиеся треки (до 20):\n" + "\n".join(
                [f"ID: {tid}. {name} (Альбом: {album if album else 'N/A'}, Исп: {author if author else 'N/A'})" for
                 tid, name, album, author in tracks]
            )
        else:
            text = "У вас нет понравившихся треков."
        await callback_query.message.answer(text)
    except Exception as e:
        logging.error(f"Ошибка получения понравившихся треков: {e}")
        await callback_query.message.answer("❌ Ошибка при получении понравившихся треков.")
    await callback_query.answer()


# --- Add Sub-menu Handlers ---
@dp.callback_query(lambda c: c.data == 'add_menu_track_cmd')
async def handle_add_menu_track_cmd(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    await callback_query.message.answer(
        "Для добавления трека, используйте команду:\n`/add_track <название> <album_id> <playlist_id> <tag_id> [mp3_ссылка]`\n(IDs должны существовать в базе).",
        parse_mode="MarkdownV2")
    await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'add_menu_playlist_cmd')
async def handle_add_menu_playlist_cmd(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    await callback_query.message.answer("Для создания плейлиста, используйте команду:\n`/create_playlist <название>`",
                                        parse_mode="MarkdownV2")
    await callback_query.answer()


# --- Account Sub-menu Handlers ---
@dp.callback_query(lambda c: c.data == 'account_info_opt')
async def handle_account_info_opt(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    username_db = user_auth_data.get('username_db', 'N/A')
    user_id_db = user_auth_data.get('user_id_db', 'N/A')
    email = "Не удалось загрузить"
    try:
        cursor.execute("SELECT mail FROM \"user\" WHERE id = %s", (user_id_db,))
        email_row = cursor.fetchone()
        if email_row: email = email_row[0]
    except Exception as e:
        logging.error(f"Ошибка получения email для информации об аккаунте: {e}")

    await callback_query.message.answer(
        f"👤 Информация об аккаунте:\nUsername: {username_db}\nEmail: {email}\nID в системе: {user_id_db}")
    await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'account_logout_opt')
async def handle_account_logout_opt(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.edit_text("✅ Вы успешно вышли из системы.")
    await callback_query.answer()
    await send_welcome(callback_query.message, state) # Optionally show start message


# --- Authenticated Commands ---
@dp.message(Command("logout"))
async def process_logout_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await message.reply("✅ Вы успешно вышли из системы.")
    await send_welcome(message, state)


@dp.message(Command("create_playlist"))
async def create_playlist_cmd(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        return

    user_id_db = user_auth_data.get('user_id_db')
    args = message.get_args()
    if not args:
        await message.reply("❌ Пожалуйста, укажите название плейлиста: /create_playlist <название>")
        return
    title = args

    try:
        cursor.execute(
            "INSERT INTO playlist (title, cover, user_id) VALUES (%s, %s, %s) RETURNING id",
            (title, '', user_id_db)
        )
        playlist_db_id = cursor.fetchone()[0]
        conn.commit()
        await message.reply(f"✅ Плейлист '{title}' (ID: {playlist_db_id}) создан.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка создания плейлиста: {e}")
        await message.reply("❌ Ошибка при создании плейлиста.")


@dp.message(Command("my_playlists"))
async def list_my_playlists(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        return

    user_id_db = user_auth_data.get('user_id_db')
    try:
        cursor.execute("SELECT id, title FROM playlist WHERE user_id = %s ORDER BY title", (user_id_db,))
        rows = cursor.fetchall()
        if rows:
            text = "📜 Ваши плейлисты:\n" + "\n".join([f"ID: {pid} - {title}" for pid, title in rows])
        else:
            text = "У вас нет плейлистов. Создайте новый с помощью /create_playlist <название>"
        await message.reply(text)
    except Exception as e:
        logging.error(f"Ошибка получения плейлистов: {e}")
        await message.reply("❌ Ошибка при получении списка плейлистов.")


@dp.message(Command("add_track"))
async def add_track_cmd(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        return
    args = message.text.split(maxsplit=5)
    if len(args) < 5:
        await message.reply("❌ Использование: /add_track <название> <album_id> <playlist_id> <tag_id> [mp3_ссылка]")
        return

    _, name, album_id_str, playlist_id_str, tag_id_str = args[:5]
    mp3_link = args[5] if len(args) > 5 else ''

    if not (album_id_str.isdigit() and playlist_id_str.isdigit() and tag_id_str.isdigit()):
        await message.reply("❌ ID альбома, плейлиста и тега должны быть числами.")
        return

    album_id = int(album_id_str)
    playlist_id = int(playlist_id_str)
    tag_id = int(tag_id_str)

    try:
        cursor.execute("SELECT id FROM album WHERE id = %s", (album_id,))
        if not cursor.fetchone():
            await message.reply(f"❌ Альбом с ID {album_id} не найден.")
            return
        cursor.execute("SELECT id FROM playlist WHERE id = %s", (playlist_id,))
        if not cursor.fetchone():
            await message.reply(f"❌ Плейлист с ID {playlist_id} не найден (для первичной привязки трека).")
            return
        cursor.execute("SELECT id FROM tag WHERE id = %s", (tag_id,))
        if not cursor.fetchone():
            await message.reply(f"❌ Тег с ID {tag_id} не найден (для первичной привязки трека).")
            return

        cursor.execute(
            """INSERT INTO track ("name", auditions, mp3, playlist_id, tag_id, album_id)
               VALUES (%s, 0, %s, %s, %s, %s) RETURNING id""",
            (name, mp3_link, playlist_id, tag_id, album_id)
        )
        track_db_id = cursor.fetchone()[0]
        conn.commit()
        await message.reply(f"✅ Трек '{name}' (ID: {track_db_id}) добавлен.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка добавления трека: {e}")
        await message.reply(f"❌ Ошибка при добавлении трека. {e}")


@dp.message(Command("add_track_to_playlist"))
async def add_track_to_playlist_cmd(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        return

    user_id_db = user_auth_data.get('user_id_db')
    args = message.get_args().split()
    if len(args) != 2:
        await message.reply("❌ Использование: /add_track_to_playlist <playlist_id> <track_id>")
        return

    playlist_id_str, track_id_str = args
    if not (playlist_id_str.isdigit() and track_id_str.isdigit()):
        await message.reply("❌ ID плейлиста и трека должны быть числами.")
        return

    playlist_id = int(playlist_id_str)
    track_id = int(track_id_str)

    try:
        cursor.execute("SELECT id FROM playlist WHERE id = %s AND user_id = %s",
                       (playlist_id, user_id_db))
        if not cursor.fetchone():
            await message.reply("❌ Плейлист не найден или не принадлежит вам.")
            return

        cursor.execute("SELECT id FROM track WHERE id = %s", (track_id,))
        if not cursor.fetchone():
            await message.reply(f"❌ Трек с ID {track_id} не найден.")
            return

        cursor.execute(
            "INSERT INTO playlist_tracklist (playlist_id, track_id) VALUES (%s, %s)",
            (playlist_id, track_id)
        )
        conn.commit()
        await message.reply(f"✅ Трек (ID: {track_id}) добавлен в плейлист (ID: {playlist_id}).")
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        await message.reply("ℹ️ Этот трек уже есть в этом плейлисте.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка добавления трека в плейлист: {e}")
        await message.reply(f"❌ Ошибка: {e}")


@dp.message(Command("like_track"))
async def like_track_cmd(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        return

    user_id_db = user_auth_data.get('user_id_db')
    track_id_str = message.get_args()

    if not track_id_str or not track_id_str.isdigit():
        await message.reply("❌ Использование: /like_track <track_id>")
        return
    track_id = int(track_id_str)

    try:
        cursor.execute("SELECT id FROM track WHERE id = %s", (track_id,))
        if not cursor.fetchone():
            await message.reply(f"❌ Трек с ID {track_id} не найден.")
            return

        cursor.execute("SELECT id FROM reactions WHERE type = 'like'")
        reaction_like_row = cursor.fetchone()
        if not reaction_like_row:
            await message.reply(
                "❌ Тип реакции 'like' не найден в системе.")
            return
        reaction_like_id = reaction_like_row[0]

        cursor.execute(
            """INSERT INTO user_reaction (user_id, reaction_id, track_id, playlist_id, album_id, author_id)
               VALUES (%s, %s, %s, NULL, NULL, NULL)""",
            (user_id_db, reaction_like_id, track_id)
        )
        conn.commit()
        await message.reply(f"❤️ Трек (ID: {track_id}) понравился!")
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        await message.reply("ℹ️ Вы уже лайкнули этот трек или другая подобная реакция существует.")
    except psycopg2.errors.ForeignKeyViolation as fk_error:
        conn.rollback()
        logging.error(f"Ошибка внешнего ключа при лайке: {fk_error}")
        await message.reply(f"❌ Ошибка данных при попытке лайкнуть трек.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка при лайке трека: {e}")
        await message.reply(f"❌ Ошибка: {e}")


@dp.message(Command("list_tracks"))
async def list_tracks_cmd(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        return
    try:
        cursor.execute("SELECT id, name, auditions FROM track ORDER BY name LIMIT 20")
        tracks = cursor.fetchall()
        if tracks:
            text = "🎶 Список треков (до 20):\n" + "\n".join(
                [f"ID: {tid}. {name} (Прослушиваний: {aud}) " for tid, name, aud in tracks])
        else:
            text = "Нет доступных треков."
        await message.reply(text)
    except Exception as e:
        logging.error(f"Ошибка получения списка треков: {e}")
        await message.reply("❌ Ошибка при получении списка треков.")


async def main():
    if not conn or not cursor:
        logging.critical("Не удалось подключиться к базе данных. Запуск бота невозможен.")
        return
    logging.info("Starting bot polling...")
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())