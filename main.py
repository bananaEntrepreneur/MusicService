import logging
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, \
    StateFilter  # StateFilter might not be used directly if all states are handled by explicit state checks
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import asyncio

API_TOKEN = '8162663853:AAHasVnLHU5bkyWVAHlWZxGXNy2uNn-O58w'  # Replace with your actual token

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


class PlaylistCreationStates(StatesGroup):
    waiting_for_playlist_title = State()
    adding_tracks = State()
    select_track_from_multiple = State()  # For clarifying track choice
    adding_tags = State()


# --- Меню ---
def get_main_menu_markup():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Поиск 🔎", callback_data="main_menu_search")],
        [types.InlineKeyboardButton(text="Моя библиотека 📚", callback_data="main_menu_library")],
        [types.InlineKeyboardButton(text="Добавить ➕", callback_data="main_menu_add")],
        [types.InlineKeyboardButton(text="Аккаунт 👤", callback_data="main_menu_account")],
        [types.InlineKeyboardButton(text="Рекомендации 🌟", callback_data="main_menu_recommendations")]
    ])


def get_search_menu_markup():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Поиск треков", callback_data="search_tracks_opt")],
        [types.InlineKeyboardButton(text="Поиск альбомов", callback_data="search_albums_opt")],
        [types.InlineKeyboardButton(text="Поиск исполнителей", callback_data="search_artists_opt")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu_back")]
    ])


def get_recommendations_menu_markup():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🏆 Топ-10 треков", callback_data="recomm_top_10_tracks")],
        [types.InlineKeyboardButton(text="🎧 Для вас (по тегам)", callback_data="recomm_user_tags")],
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
    # Clear all states for the user to ensure a fresh start, but only if coming via /start
    # If user is already logged in and types /start, this will log them out.
    # Consider if this is desired behavior or if /start should check auth state first.
    await state.clear()  # Clears all FSM data for this user/chat including auth.
    await message.reply("🎵 Добро пожаловать в музыкальный сервис Bot!")
    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Авторизация (Вход)", callback_data="auth_login_start")],
        [types.InlineKeyboardButton(text="Регистрация", callback_data="auth_register_start")]
    ])
    await message.answer(
        f"Привет, {message.from_user.full_name}! Пожалуйста, войдите или зарегистрируйтесь.",
        reply_markup=markup
    )


# --- Регистрация ---
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
        await state.set_state(None)  # Clear current FSM group state
        return
    reg_password = message.text
    if len(reg_password) > 32:
        await message.answer("Пароль слишком длинный. Пожалуйста, введите пароль до 32 символов:")
        return  # Remain in current state

    user_data_reg = await state.get_data()
    reg_email = user_data_reg.get('reg_email')
    reg_username = user_data_reg.get('reg_username')

    try:
        cursor.execute("SELECT id FROM \"user\" WHERE username = %s OR mail = %s", (reg_username, reg_email))
        if cursor.fetchone():
            await message.reply(
                "ℹ️ Пользователь с таким username или email уже существует. Попробуйте другие данные или /login.")
            await state.set_state(None)
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
        await state.set_state(None)  # Clear current FSM group state


# --- Логин ---
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
        await state.set_state(None)  # Clear current FSM group state
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
            # Store auth data in FSM context (will persist until state.clear() or explicit removal)
            await state.update_data(user_id_db=user_id_db, username_db=username_db, authenticated=True)
            await state.set_state(None)  # Clear AuthStates group, but keep FSM data
            await message.answer(f"✅ Авторизация успешна, {username_db}!")
            await message.answer("Главное меню:", reply_markup=get_main_menu_markup())
        else:
            await message.answer("❌ Неверный username или пароль. Попробуйте снова или /register.")
            # Don't clear all data, just the login attempt specific data if any, and clear the AuthStates
            await state.set_state(None)
    except Exception as e:
        logging.error(f"Ошибка авторизации: {e}")
        await message.reply("❌ Ошибка при авторизации. Попробуйте позже.")
        await state.set_state(None)


# --- Обработчики главного меню ---
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
        [types.InlineKeyboardButton(text="➕ Создать новый плейлист",
                                    callback_data="create_playlist_interactive_start")],
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
        [types.InlineKeyboardButton(text="Создать плейлист (интерактивно)",
                                    callback_data="create_playlist_interactive_start")],
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


@dp.callback_query(lambda c: c.data == 'main_menu_recommendations')
async def handle_menu_recommendations(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    await callback_query.message.edit_text("Рекомендации:", reply_markup=get_recommendations_menu_markup())
    await callback_query.answer()


# --- Поиск: Подменю и обработчики FSM ---
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
        await state.set_state(None)
        return

    query = message.text
    try:
        cursor.execute(
            """SELECT t.id, t.name, al.title as album_name, au.name as author_name, al.author_id
               FROM track t
                        LEFT JOIN album al ON t.album_id = al.id
                        LEFT JOIN author au ON al.author_id = au.id
               WHERE t.name ILIKE %s
                   LIMIT 5""",
            (f'%{query}%',)
        )
        tracks = cursor.fetchall()
        if tracks:
            await message.answer("🎶 Найденные треки:")
            for tid, name, album_name, author_name, author_id_val in tracks:
                track_text = f"ID: {tid}. {name}\n(Альбом: {album_name if album_name else 'N/A'}, Исп: {author_name if author_name else 'N/A'})"
                buttons = [types.InlineKeyboardButton(text="👍 Like", callback_data=f"like_track_{tid}")]
                if author_id_val:
                    buttons.append(
                        types.InlineKeyboardButton(text="👤 Автор", callback_data=f"view_author_{author_id_val}"))

                markup = types.InlineKeyboardMarkup(inline_keyboard=[buttons])
                await message.answer(track_text, reply_markup=markup)
        else:
            await message.answer("❌ Треки с таким названием не найдены.")
    except Exception as e:
        logging.error(f"Ошибка поиска треков: {e}")
        await message.answer("❌ Произошла ошибка при поиске треков.")
    finally:
        await state.set_state(None)  # Clear only SearchStates
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
        await state.set_state(None)
        return
    query = message.text
    try:
        cursor.execute(
            """SELECT al.id, al.title, au.name as author_name, g.name as genre_name, al.author_id
               FROM album al
                        LEFT JOIN author au ON al.author_id = au.id
                        LEFT JOIN genre g ON al.genre_id = g.id
               WHERE al.title ILIKE %s
                   LIMIT 5""",
            (f'%{query}%',)
        )
        albums = cursor.fetchall()
        if albums:
            await message.answer("💿 Найденные альбомы:")
            for aid, title, author_name, genre_name, author_id_val in albums:
                album_text = f"ID: {aid}. {title}\n(Исполнитель: {author_name if author_name else 'N/A'}, Жанр: {genre_name if genre_name else 'N/A'})"
                buttons = [types.InlineKeyboardButton(text="👍 Like Альбом", callback_data=f"like_album_{aid}")]
                if author_id_val:
                    buttons.append(
                        types.InlineKeyboardButton(text="👤 К автору", callback_data=f"view_author_{author_id_val}"))
                buttons.append(
                    types.InlineKeyboardButton(text="🎼 Треки альбома", callback_data=f"list_tracks_for_album_{aid}"))
                markup = types.InlineKeyboardMarkup(inline_keyboard=[buttons])
                await message.answer(album_text, reply_markup=markup)
        else:
            await message.answer("❌ Альбомы с таким названием не найдены.")
    except Exception as e:
        logging.error(f"Ошибка поиска альбомов: {e}")
        await message.answer("❌ Произошла ошибка при поиске альбомов.")
    finally:
        await state.set_state(None)
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
        await state.set_state(None)
        return
    query = message.text
    try:
        cursor.execute(
            """SELECT id, name, auditions, bio
               FROM author
               WHERE name ILIKE %s
                   LIMIT 5""",
            (f'%{query}%',)
        )
        artists = cursor.fetchall()
        if artists:
            await message.answer("🎤 Найденные исполнители:")
            for aid, name, auditions, bio in artists:
                artist_text = f"ID: {aid}. {name}\nПрослушиваний: {auditions if auditions else 0}\nBIO: {bio if bio else 'N/A'}"
                buttons = [
                    types.InlineKeyboardButton(text="👍 Like Исполнителя", callback_data=f"like_author_{aid}"),
                    types.InlineKeyboardButton(text="🛍️ Мерч", callback_data=f"view_merch_{aid}"),
                    types.InlineKeyboardButton(text="🎤 Концерты", callback_data=f"view_concerts_{aid}")
                ]
                markup = types.InlineKeyboardMarkup(inline_keyboard=[buttons])
                await message.answer(artist_text, reply_markup=markup)
        else:
            await message.answer("❌ Исполнители с таким именем не найдены.")
    except Exception as e:
        logging.error(f"Ошибка поиска исполнителей: {e}")
        await message.answer("❌ Произошла ошибка при поиске исполнителей.")
    finally:
        await state.set_state(None)
        await message.answer("Меню поиска:", reply_markup=get_search_menu_markup())


# --- Generic Like Handler & View Author Handler ---
@dp.callback_query(lambda c: c.data.startswith('like_'))
async def handle_like_entity(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    user_id_db = user_auth_data.get('user_id_db')

    try:
        parts = callback_query.data.split('_')
        entity_type = parts[1]
        entity_id = int(parts[2])

        cursor.execute("SELECT id FROM reactions WHERE type = 'like'")
        reaction_like_row = cursor.fetchone()
        if not reaction_like_row:
            await callback_query.answer("❌ Тип реакции 'like' не найден в системе.", show_alert=True)
            return
        reaction_like_id = reaction_like_row[0]

        sql_insert = """INSERT INTO user_reaction (user_id, reaction_id, track_id, album_id, author_id)
                        VALUES (%s, %s, %s, %s, %s)"""
        track_id_val, album_id_val, author_id_val = None, None, None

        if entity_type == 'track':
            track_id_val = entity_id
            cursor.execute("SELECT id FROM track WHERE id = %s", (entity_id,))
            if not cursor.fetchone():
                await callback_query.answer(f"Трек ID {entity_id} не найден.", show_alert=True)
                return
        elif entity_type == 'album':
            album_id_val = entity_id
            cursor.execute("SELECT id FROM album WHERE id = %s", (entity_id,))
            if not cursor.fetchone():
                await callback_query.answer(f"Альбом ID {entity_id} не найден.", show_alert=True)
                return
        elif entity_type == 'author':
            author_id_val = entity_id
            cursor.execute("SELECT id FROM author WHERE id = %s", (entity_id,))
            if not cursor.fetchone():
                await callback_query.answer(f"Автор ID {entity_id} не найден.", show_alert=True)
                return
        else:
            await callback_query.answer("Неизвестный тип для лайка.", show_alert=True)
            return

        cursor.execute(sql_insert, (user_id_db, reaction_like_id, track_id_val, album_id_val, author_id_val))
        conn.commit()
        await callback_query.answer(f"{entity_type.capitalize()} ID {entity_id} понравился!", show_alert=False)

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        await callback_query.answer("Вы уже лайкнули это.", show_alert=True)
    except psycopg2.errors.ForeignKeyViolation as fk_error:
        conn.rollback()
        logging.error(f"Ошибка внешнего ключа при лайке: {fk_error}")
        await callback_query.answer("Ошибка данных при попытке лайкнуть.", show_alert=True)
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка при лайке сущности: {e}")
        await callback_query.answer("Произошла ошибка.", show_alert=True)


@dp.callback_query(lambda c: c.data.startswith('view_author_'))
async def handle_view_author(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return

    try:
        author_id = int(callback_query.data.split('_')[-1])  # Allow for view_author_fromalbum_ID etc.
        cursor.execute("SELECT id, name, auditions, bio FROM author WHERE id = %s", (author_id,))
        author_data = cursor.fetchone()

        if author_data:
            aid, name, auditions, bio = author_data
            text = f"👤 Исполнитель: {name}\nID: {aid}\nПрослушиваний: {auditions if auditions else 0}\nBIO: {bio if bio else 'N/A'}"

            author_actions_markup = types.InlineKeyboardMarkup(inline_keyboard=[
                [
                    types.InlineKeyboardButton(text="👍 Like Исполнителя", callback_data=f"like_author_{aid}"),
                    types.InlineKeyboardButton(text="🛍️ Мерч", callback_data=f"view_merch_{aid}"),
                ],
                [types.InlineKeyboardButton(text="🎤 Концерты", callback_data=f"view_concerts_{aid}")]
            ])
            await callback_query.message.answer(text, reply_markup=author_actions_markup)
        else:
            await callback_query.message.answer("Информация об исполнителе не найдена.")
    except Exception as e:
        logging.error(f"Ошибка при просмотре автора: {e}")
        await callback_query.message.answer("Не удалось загрузить информацию об авторе.")
    await callback_query.answer()


# Placeholder handlers
@dp.callback_query(lambda c: c.data.startswith('list_tracks_for_album_'))
async def handle_list_tracks_for_album(callback_query: types.CallbackQuery, state: FSMContext):
    album_id = callback_query.data.split('_')[-1]
    await callback_query.message.answer(f"Здесь будут треки для альбома ID {album_id}. (Не реализовано)")
    await callback_query.answer()


@dp.callback_query(lambda c: c.data.startswith('view_merch_'))
async def handle_view_merch(callback_query: types.CallbackQuery, state: FSMContext):
    author_id = callback_query.data.split('_')[-1]
    await callback_query.message.answer(f"Здесь будет мерч для исполнителя ID {author_id}. (Не реализовано)")
    await callback_query.answer()


@dp.callback_query(lambda c: c.data.startswith('view_concerts_'))
async def handle_view_concerts(callback_query: types.CallbackQuery, state: FSMContext):
    author_id = callback_query.data.split('_')[-1]
    await callback_query.message.answer(f"Здесь будут концерты для исполнителя ID {author_id}. (Не реализовано)")
    await callback_query.answer()


# --- Обработчики подменю "Библиотека" ---
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
                         AND ur.track_id IS NOT NULL
                       ORDER BY t.name LIMIT 20
                       """, (user_id_db,))
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


# --- Обработчики подменю "Добавить" ---
@dp.callback_query(lambda c: c.data == 'add_menu_track_cmd')
async def handle_add_menu_track_cmd(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    await callback_query.message.answer(
        "Для добавления трека, используйте команду:\n`/add_track <название> <album_id> <playlist_id> <tag_id> [mp3_ссылка]`\n(IDs должны существовать в базе).",
        parse_mode="MarkdownV2")
    await callback_query.answer()


# Updated to start interactive playlist creation
@dp.callback_query(lambda c: c.data == 'create_playlist_interactive_start')
async def handle_create_playlist_interactive_start(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:  # Edit previous message if possible
        await callback_query.message.edit_text("Создание нового плейлиста. Введите название для вашего плейлиста:")
    except:  # Send new if edit fails
        await callback_query.message.answer("Создание нового плейлиста. Введите название для вашего плейлиста:")
    await state.set_state(PlaylistCreationStates.waiting_for_playlist_title)
    await callback_query.answer()


# --- Обработчики подменю "Аккаунт" ---
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
    # Clear all FSM data for this user, effectively logging them out
    await state.clear()
    try:
        await callback_query.message.edit_text("✅ Вы успешно вышли из системы.")
    except:
        await callback_query.message.answer("✅ Вы успешно вышли из системы.")
    await callback_query.answer()
    # Optionally, send the initial /start message again to prompt for login/register
    # await send_welcome(callback_query.message, state)


# --- Обработчики подменю "Рекомендации" ---
@dp.callback_query(lambda c: c.data == 'recomm_top_10_tracks')
async def handle_recomm_top_10_tracks(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        cursor.execute(
            """SELECT t.id, t.name, t.auditions, al.title as album_name, au.name as author_name
               FROM track t
                        LEFT JOIN album al ON t.album_id = al.id
                        LEFT JOIN author au ON al.author_id = au.id
               ORDER BY t.auditions DESC NULLS LAST LIMIT 10"""
        )
        tracks = cursor.fetchall()
        if tracks:
            response_text = "🏆 Топ-10 треков по прослушиваниям:\n\n"
            for tid, name, auditions, album_name, author_name in tracks:
                response_text += (
                    f"🎵 {name} (ID: {tid})\n"
                    f"   Альбом: {album_name if album_name else 'N/A'}, Исп: {author_name if author_name else 'N/A'}\n"
                    f"   Прослушиваний: {auditions if auditions is not None else 0}\n\n"
                )
        else:
            response_text = "Не удалось получить топ-10 треков."
        await callback_query.message.answer(response_text)
    except Exception as e:
        logging.error(f"Ошибка получения топ-10 треков: {e}")
        await callback_query.message.answer("❌ Произошла ошибка при получении топ-10 треков.")
    await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'recomm_user_tags')
async def handle_recomm_user_tags(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    user_id_db = user_auth_data.get('user_id_db')

    try:
        cursor.execute(
            """SELECT DISTINCT tt.tag_id
               FROM user_reaction ur
                        JOIN reactions react ON ur.reaction_id = react.id
                        JOIN track t ON ur.track_id = t.id
                        JOIN track_tag tt ON t.id = tt.track_id
               WHERE ur.user_id = %s
                 AND react.type = 'like'
                 AND ur.track_id IS NOT NULL""",
            (user_id_db,)
        )
        liked_tags_rows = cursor.fetchall()
        if not liked_tags_rows:
            await callback_query.message.answer(
                "Не найдено понравившихся треков с тегами для создания рекомендаций. Полайкайте больше треков!")
            await callback_query.answer()
            return

        liked_tag_ids = [row[0] for row in liked_tags_rows]

        cursor.execute(
            """SELECT t.id,
                      t.name,
                      COUNT(DISTINCT tt.tag_id) as matching_tags,
                      t.auditions,
                      al.title                  as album_name,
                      au.name                   as author_name
               FROM track t
                        JOIN track_tag tt ON t.id = tt.track_id
                        LEFT JOIN album al ON t.album_id = al.id
                        LEFT JOIN author au ON al.author_id = au.id
               WHERE tt.tag_id = ANY (%s)
                 AND t.id NOT IN (SELECT ur_liked.track_id
                                  FROM user_reaction ur_liked
                                           JOIN reactions react_liked ON ur_liked.reaction_id = react_liked.id
                                  WHERE ur_liked.user_id = %s
                                    AND react_liked.type = 'like'
                                    AND ur_liked.track_id IS NOT NULL)
               GROUP BY t.id, t.name, t.auditions, al.title, au.name
               ORDER BY matching_tags DESC, t.auditions DESC NULLS LAST LIMIT 5""",
            (liked_tag_ids, user_id_db)
        )
        recommended_tracks = cursor.fetchall()

        if recommended_tracks:
            response_text = "🎧 Рекомендованные треки на основе ваших предпочтений (по тегам):\n\n"
            for tid, name, matching_tags, auditions, album_name, author_name in recommended_tracks:
                response_text += (
                    f"🎵 {name} (ID: {tid})\n"
                    f"   Альбом: {album_name if album_name else 'N/A'}, Исп: {author_name if author_name else 'N/A'}\n"
                    f"   Совпадающих тегов: {matching_tags}, Прослушиваний: {auditions if auditions is not None else 0}\n\n"
                )
        else:
            response_text = "Не удалось подобрать персональные рекомендации. Возможно, стоит расширить список понравившихся треков."
        await callback_query.message.answer(response_text)
    except Exception as e:
        logging.error(f"Ошибка получения персональных рекомендаций: {e}")
        await callback_query.message.answer("❌ Произошла ошибка при подборе рекомендаций.")
    await callback_query.answer()


# --- Интерактивное создание плейлиста ---
@dp.message(PlaylistCreationStates.waiting_for_playlist_title)
async def process_playlist_title(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        await state.set_state(None)
        return

    playlist_title = message.text.strip()
    if not playlist_title:
        await message.reply("Название плейлиста не может быть пустым. Попробуйте еще раз:")
        return  # Remain in current state

    user_id_db = user_auth_data.get('user_id_db')
    try:
        cursor.execute(
            "INSERT INTO playlist (title, user_id, cover) VALUES (%s, %s, %s) RETURNING id",
            (playlist_title, user_id_db, '')  # cover can be empty for now
        )
        new_playlist_id = cursor.fetchone()[0]
        conn.commit()
        await state.update_data(new_playlist_id=new_playlist_id, playlist_title=playlist_title)
        await message.answer(
            f"Плейлист '{playlist_title}' (ID: {new_playlist_id}) создан.\n"
            "Теперь добавьте треки. Введите ID или название трека.\n"
            "Когда закончите добавление треков, напишите /done_tracks."
        )
        await state.set_state(PlaylistCreationStates.adding_tracks)
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка создания плейлиста (DB): {e}")
        await message.reply("❌ Не удалось создать плейлист. Попробуйте позже.")
        await state.set_state(None)


@dp.message(Command("done_tracks"), PlaylistCreationStates.adding_tracks)
async def process_done_adding_tracks(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        await state.set_state(None)
        return

    playlist_data = await state.get_data()
    playlist_title = playlist_data.get('playlist_title', 'Ваш плейлист')

    await message.answer(
        f"Добавление треков в плейлист '{playlist_title}' завершено.\n"
        "Теперь добавьте теги к плейлисту. Введите название тега.\n"
        "Когда закончите добавление тегов, напишите /done_tags."
    )
    await state.set_state(PlaylistCreationStates.adding_tags)


@dp.message(PlaylistCreationStates.adding_tracks)
async def process_add_track_to_new_playlist(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        await state.set_state(None)
        return

    playlist_data = await state.get_data()
    new_playlist_id = playlist_data.get('new_playlist_id')
    if not new_playlist_id:
        await message.reply("Произошла ошибка, ID плейлиста не найден. Пожалуйста, начните создание плейлиста заново.")
        await state.set_state(None)
        return

    track_input = message.text.strip()
    found_track_id = None
    found_track_name = None

    try:
        if track_input.isdigit():  # User provided an ID
            track_id_candidate = int(track_input)
            cursor.execute("SELECT id, name FROM track WHERE id = %s", (track_id_candidate,))
            track_record = cursor.fetchone()
            if track_record:
                found_track_id, found_track_name = track_record
            else:
                await message.reply(f"Трек с ID {track_id_candidate} не найден. Попробуйте другое ID или название.")
                return
        else:  # User provided a name
            cursor.execute(
                "SELECT id, name FROM track WHERE name ILIKE %s",
                (f'%{track_input}%',)
            )
            tracks_found = cursor.fetchall()
            if not tracks_found:
                await message.reply(f"Трек с названием '{track_input}' не найден. Попробуйте другое название или ID.")
                return
            if len(tracks_found) == 1:
                found_track_id, found_track_name = tracks_found[0]
            else:
                # Multiple tracks found, ask user to specify
                response_text = "Найдено несколько треков. Пожалуйста, выберите один, отправив его ID:\n"
                options = []
                for tid, tname in tracks_found[:5]:  # Limit options displayed
                    response_text += f"ID: {tid} - {tname}\n"
                    options.append({'id': tid, 'name': tname})
                await state.update_data(track_selection_options=options)  # Store options for next step
                # For simplicity here, just ask to re-enter ID from the list. A button based selection would be better.
                await message.reply(response_text + "\nПожалуйста, введите ID выбранного трека.")
                # A more robust FSM would go to a new state like PlaylistCreationStates.select_track_from_multiple
                # For now, user has to re-enter the ID in the current adding_tracks state.
                return

        if found_track_id and found_track_name:
            cursor.execute(
                "INSERT INTO playlist_tracklist (playlist_id, track_id) VALUES (%s, %s)",
                (new_playlist_id, found_track_id)
            )
            conn.commit()
            await message.reply(f"Трек '{found_track_name}' (ID: {found_track_id}) добавлен в плейлист. "
                                "Введите следующий или /done_tracks.")
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        await message.reply(f"Трек '{found_track_name}' уже есть в этом плейлисте. Введите другой или /done_tracks.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка добавления трека в новый плейлист: {e}")
        await message.reply("❌ Произошла ошибка при добавлении трека.")


@dp.message(Command("done_tags"), PlaylistCreationStates.adding_tags)
async def process_done_adding_tags(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        await state.set_state(None)
        return

    playlist_data = await state.get_data()
    playlist_title = playlist_data.get('playlist_title', 'Ваш плейлист')
    new_playlist_id = playlist_data.get('new_playlist_id')

    await message.answer(f"✅ Плейлист '{playlist_title}' (ID: {new_playlist_id}) успешно создан и настроен!")
    await state.set_state(None)  # Clear PlaylistCreationStates
    await message.answer("Главное меню:", reply_markup=get_main_menu_markup())


@dp.message(PlaylistCreationStates.adding_tags)
async def process_add_tag_to_new_playlist(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        await state.set_state(None)
        return

    playlist_data = await state.get_data()
    new_playlist_id = playlist_data.get('new_playlist_id')
    if not new_playlist_id:
        await message.reply("Произошла ошибка, ID плейлиста не найден. Пожалуйста, начните создание плейлиста заново.")
        await state.set_state(None)
        return

    tag_name_input = message.text.strip()
    if not tag_name_input:
        await message.reply("Название тега не может быть пустым. Введите тег или /done_tags.")
        return

    try:
        # Check if tag exists, otherwise create it
        cursor.execute("SELECT id FROM tag WHERE name ILIKE %s", (tag_name_input,))
        tag_record = cursor.fetchone()
        if tag_record:
            tag_id = tag_record[0]
            tag_name = tag_name_input  # Or fetch exact name if case differs and desired
        else:
            cursor.execute("INSERT INTO tag (name) VALUES (%s) RETURNING id, name", (tag_name_input,))
            tag_id, tag_name = cursor.fetchone()
            conn.commit()
            await message.reply(f"Тег '{tag_name}' создан.")

        # Add tag to playlist
        cursor.execute(
            "INSERT INTO playlist_tags (playlist_id, tag_id) VALUES (%s, %s)",
            (new_playlist_id, tag_id)
        )
        conn.commit()
        await message.reply(f"Тег '{tag_name}' (ID: {tag_id}) добавлен к плейлисту. "
                            "Введите следующий или /done_tags.")
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        await message.reply(f"Тег '{tag_name_input}' уже добавлен к этому плейлисту. Введите другой или /done_tags.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка добавления тега к плейлисту: {e}")
        await message.reply("❌ Произошла ошибка при добавлении тега.")


# --- Существующие команды (адаптированы или проверены) ---
@dp.message(Command("logout"))
async def process_logout_cmd(message: types.Message, state: FSMContext):
    await state.clear()  # Clear all FSM data for this user/chat
    await message.reply("✅ Вы успешно вышли из системы.")
    # After logout, show initial welcome to allow login/register again
    await send_welcome(message, state)  # Pass state for consistency, though it's just cleared


@dp.message(Command("create_playlist"))  # Simple one-shot command, interactive is preferred via menu
async def create_playlist_cmd(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data: return
    user_id_db = user_auth_data.get('user_id_db')
    args = message.get_args()
    if not args:
        await message.reply("❌ Пожалуйста, укажите название плейлиста: /create_playlist <название>\n"
                            "Или используйте интерактивное создание через меню 'Добавить' / 'Моя Библиотека'.")
        return
    title = args
    try:
        cursor.execute(
            "INSERT INTO playlist (title, cover, user_id) VALUES (%s, %s, %s) RETURNING id",
            (title, '', user_id_db)
        )
        playlist_db_id = cursor.fetchone()[0]
        conn.commit()
        await message.reply(f"✅ Плейлист '{title}' (ID: {playlist_db_id}) создан (быстрый режим).")
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка создания плейлиста: {e}")
        await message.reply("❌ Ошибка при создании плейлиста.")


@dp.message(Command("my_playlists"))
async def list_my_playlists(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data: return
    user_id_db = user_auth_data.get('user_id_db')
    try:
        cursor.execute("SELECT id, title FROM playlist WHERE user_id = %s ORDER BY title", (user_id_db,))
        rows = cursor.fetchall()
        if rows:
            text = "📜 Ваши плейлисты:\n" + "\n".join([f"ID: {pid} - {title}" for pid, title in rows])
        else:
            text = "У вас нет плейлистов."
        await message.reply(text)
    except Exception as e:
        logging.error(f"Ошибка получения плейлистов: {e}")
        await message.reply("❌ Ошибка при получении списка плейлистов.")


@dp.message(Command("add_track"))
async def add_track_cmd(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data: return
    args = message.text.split(maxsplit=5)
    if len(args) < 5:
        await message.reply("❌ Использование: /add_track <название> <album_id> <playlist_id> <tag_id> [mp3_ссылка]")
        return
    _, name, album_id_str, playlist_id_str, tag_id_str = args[:5]
    mp3_link = args[5] if len(args) > 5 else ''
    if not (album_id_str.isdigit() and playlist_id_str.isdigit() and tag_id_str.isdigit()):
        await message.reply("❌ ID альбома, плейлиста и тега должны быть числами.")
        return
    album_id, playlist_id, tag_id = int(album_id_str), int(playlist_id_str), int(tag_id_str)
    try:
        for table, entity_id_val in [("album", album_id), ("playlist", playlist_id), ("tag", tag_id)]:
            cursor.execute(f"SELECT id FROM \"{table}\" WHERE id = %s", (entity_id_val,))
            if not cursor.fetchone():
                await message.reply(f"❌ Сущность {table} с ID {entity_id_val} не найдена.")
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
        await message.reply(f"❌ Ошибка при добавлении трека: {e}")


@dp.message(Command("add_track_to_playlist"))
async def add_track_to_playlist_cmd(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data: return
    user_id_db = user_auth_data.get('user_id_db')
    args = message.get_args().split()
    if len(args) != 2 or not args[0].isdigit() or not args[1].isdigit():
        await message.reply("❌ Использование: /add_track_to_playlist <playlist_id> <track_id>")
        return
    playlist_id, track_id = int(args[0]), int(args[1])
    try:
        cursor.execute("SELECT id FROM playlist WHERE id = %s AND user_id = %s", (playlist_id, user_id_db))
        if not cursor.fetchone():
            await message.reply("❌ Плейлист не найден или не принадлежит вам.")
            return
        cursor.execute("SELECT id FROM track WHERE id = %s", (track_id,))
        if not cursor.fetchone():
            await message.reply(f"❌ Трек с ID {track_id} не найден.")
            return
        cursor.execute("INSERT INTO playlist_tracklist (playlist_id, track_id) VALUES (%s, %s)",
                       (playlist_id, track_id))
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
    if not user_auth_data: return
    user_id_db = user_auth_data.get('user_id_db')
    track_id_str = message.get_args()
    if not track_id_str or not track_id_str.isdigit():
        await message.reply("❌ Использование: /like_track <track_id>. Рекомендуется использовать кнопки 👍.")
        return
    track_id = int(track_id_str)
    try:
        cursor.execute("SELECT id FROM reactions WHERE type = 'like'")
        reaction_like_id = cursor.fetchone()[0]  # Assumes 'like' reaction exists
        cursor.execute("INSERT INTO user_reaction (user_id, reaction_id, track_id) VALUES (%s, %s, %s)",
                       (user_id_db, reaction_like_id, track_id))
        conn.commit()
        await message.reply(f"❤️ Трек (ID: {track_id}) понравился (через команду)!")
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        await message.reply("ℹ️ Вы уже лайкнули этот трек.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка лайка трека через команду: {e}")
        await message.reply("❌ Ошибка при лайке трека.")


@dp.message(Command("list_tracks"))
async def list_tracks_cmd(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data: return
    try:
        cursor.execute("SELECT id, name, auditions FROM track ORDER BY name LIMIT 20")
        tracks = cursor.fetchall()
        if tracks:
            text = "🎶 Список треков (до 20):\n" + "\n".join(
                [f"ID: {tid}. {name} (Прослушиваний: {aud if aud is not None else 0}) " for tid, name, aud in tracks])
        else:
            text = "Нет доступных треков."
        await message.reply(text)
    except Exception as e:
        logging.error(f"Ошибка получения списка треков: {e}")
        await message.reply("❌ Ошибка при получении списка треков.")


# --- Запуск бота ---
async def main():
    if not conn or not cursor:
        logging.critical("Не удалось подключиться к базе данных. Запуск бота невозможен.")
        return
    logging.info("Starting bot polling...")
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())