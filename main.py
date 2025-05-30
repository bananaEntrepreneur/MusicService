import logging
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import asyncio

API_TOKEN = '...'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Подключение к базе данных
try:
    conn = psycopg2.connect(dbname="Music service", user="...", password="...", host="localhost")
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
    select_track_from_multiple = State()
    adding_tags = State()


class PlaylistManagementStates(StatesGroup):
    waiting_for_track_to_add_to_existing_playlist = State()


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
        [types.InlineKeyboardButton(text="🎧 Для вас", callback_data="recomm_user_tags")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu_back")]
    ])


# Хэлпер для отправки сообщения об ошибке
async def send_error_message(event: types.Message | types.CallbackQuery,
                             message_text="❌ Произошла непредвиденная ошибка. Попробуйте позже."):
    msg_target = event.message if isinstance(event, types.CallbackQuery) else event
    try:
        await msg_target.reply(message_text)
    except Exception as e_reply:
        logging.warning(f"Failed to reply with error, attempting to send: {e_reply}")
        try:
            await bot.send_message(msg_target.chat.id, message_text)
        except Exception as e_send:
            logging.error(f"Failed to send error message directly: {e_send}")

    if isinstance(event, types.CallbackQuery):
        try:
            await event.answer(message_text.split('.')[0], show_alert=True)
        except Exception as e_answer:  # CQ might have expired
            logging.warning(f"Failed to answer callback query for error: {e_answer}")


# Хэлпер для проверки авторизации
async def ensure_authenticated(message_or_cq: types.Message | types.CallbackQuery, state: FSMContext):
    if not conn or not cursor:
        msg_target = message_or_cq.message if isinstance(message_or_cq, types.CallbackQuery) else message_or_cq
        await msg_target.reply("❌ Ошибка подключения к базе данных. Действие невозможно.")
        if isinstance(message_or_cq, types.CallbackQuery): await message_or_cq.answer("DB Connection Error",
                                                                                      show_alert=True)
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
    try:
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
    except Exception as e:
        logging.error(f"Error in send_welcome: {e}")
        await send_error_message(message)


# --- Регистрация ---
@dp.callback_query(lambda c: c.data == 'auth_register_start')
async def process_register_start(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        if not conn or not cursor:
            await callback_query.message.answer("❌ Ошибка подключения к базе данных. Регистрация невозможна.")
            await callback_query.answer()
            return
        await callback_query.message.answer("📝 Регистрация нового пользователя.\nПожалуйста, введите ваш email:")
        await state.set_state(AuthStates.waiting_for_email_reg)
        await callback_query.answer()
    except Exception as e:
        logging.error(f"Error in process_register_start: {e}")
        await send_error_message(callback_query)


@dp.message(AuthStates.waiting_for_email_reg)
async def process_email_reg(message: types.Message, state: FSMContext):
    try:
        await state.update_data(reg_email=message.text)
        await message.answer("Введите username:")
        await state.set_state(AuthStates.waiting_for_username_reg)
    except Exception as e:
        logging.error(f"Error in process_email_reg: {e}")
        await send_error_message(message)
        await state.clear()


@dp.message(AuthStates.waiting_for_username_reg)
async def process_username_reg(message: types.Message, state: FSMContext):
    try:
        await state.update_data(reg_username=message.text)
        await message.answer("Придумайте пароль (макс. 32 символа):")
        await state.set_state(AuthStates.waiting_for_password_reg)
    except Exception as e:
        logging.error(f"Error in process_username_reg: {e}")
        await send_error_message(message)
        await state.clear()


@dp.message(AuthStates.waiting_for_password_reg)
async def process_password_reg(message: types.Message, state: FSMContext):
    try:
        if not conn or not cursor:
            await message.reply("❌ Ошибка подключения к базе данных. Регистрация не удалась.")
            await state.set_state(None)
            return
        reg_password = message.text
        if len(reg_password) > 32:
            await message.answer("Пароль слишком длинный. Пожалуйста, введите пароль до 32 символов:")
            return

        user_data_reg = await state.get_data()
        reg_email = user_data_reg.get('reg_email')
        reg_username = user_data_reg.get('reg_username')

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
    except psycopg2.Error as db_err:
        conn.rollback()
        logging.error(f"Database error in process_password_reg: {db_err}")
        await message.reply("❌ Ошибка при регистрации (база данных). Попробуйте позже.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Unexpected error in process_password_reg: {e}")
        await send_error_message(message, "❌ Ошибка при регистрации. Попробуйте позже.")
    finally:
        await state.set_state(None)


# --- Логин ---
@dp.callback_query(lambda c: c.data == 'auth_login_start')
@dp.message(Command("login"))
async def process_login_start(event: types.Message | types.CallbackQuery, state: FSMContext):
    try:
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
    except Exception as e:
        logging.error(f"Error in process_login_start: {e}")
        await send_error_message(event)
        await state.clear()


@dp.message(AuthStates.waiting_for_username_login)
async def process_username_login(message: types.Message, state: FSMContext):
    try:
        await state.update_data(login_username=message.text)
        await message.answer("Теперь введите ваш пароль:")
        await state.set_state(AuthStates.waiting_for_password_login)
    except Exception as e:
        logging.error(f"Error in process_username_login: {e}")
        await send_error_message(message)
        await state.clear()


@dp.message(AuthStates.waiting_for_password_login)
async def process_password_login(message: types.Message, state: FSMContext):
    try:
        if not conn or not cursor:
            await message.reply("❌ Ошибка подключения к базе данных. Вход не удался.")
            await state.set_state(None)
            return

        user_data_login = await state.get_data()
        input_username = user_data_login.get('login_username')
        input_password = message.text

        cursor.execute(
            "SELECT id, username FROM \"user\" WHERE username = %s AND password = %s",
            (input_username, input_password)
        )
        db_user = cursor.fetchone()

        if db_user:
            user_id_db, username_db = db_user
            await state.update_data(user_id_db=user_id_db, username_db=username_db, authenticated=True)
            await state.set_state(None)
            await message.answer(f"✅ Авторизация успешна, {username_db}!")
            await message.answer("Главное меню:", reply_markup=get_main_menu_markup())
        else:
            await message.answer("❌ Неверный username или пароль. Попробуйте снова или /register.")
            await state.set_state(None)
    except psycopg2.Error as db_err:
        logging.error(f"Database error in process_password_login: {db_err}")
        await message.reply("❌ Ошибка при авторизации (база данных). Попробуйте позже.")
        await state.set_state(None)
    except Exception as e:
        logging.error(f"Unexpected error in process_password_login: {e}")
        await send_error_message(message, "❌ Ошибка при авторизации. Попробуйте позже.")
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
    finally:
        await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'main_menu_search')
async def handle_menu_search(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        await callback_query.message.edit_text("Меню поиска:", reply_markup=get_search_menu_markup())
    except Exception as e:
        logging.error(f"Error in handle_menu_search: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'main_menu_library')
async def handle_menu_library(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        library_markup = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Мои плейлисты", callback_data="library_my_playlists")],
            [types.InlineKeyboardButton(text="Понравившиеся треки", callback_data="library_liked_tracks")],
            [types.InlineKeyboardButton(text="➕ Создать новый плейлист",
                                        callback_data="create_playlist_interactive_start")],
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu_back")]
        ])
        await callback_query.message.edit_text("Моя библиотека:", reply_markup=library_markup)
    except Exception as e:
        logging.error(f"Error in handle_menu_library: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'main_menu_add')
async def handle_menu_add(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        add_markup = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Добавить трек", callback_data="add_menu_track_cmd")],
            [types.InlineKeyboardButton(text="Создать плейлист",
                                        callback_data="create_playlist_interactive_start")],
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu_back")]
        ])
        await callback_query.message.edit_text("Что вы хотите добавить?", reply_markup=add_markup)
    except Exception as e:
        logging.error(f"Error in handle_menu_add: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'main_menu_account')
async def handle_menu_account(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        username_db = user_auth_data.get('username_db', 'N/A')
        account_markup = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Информация об аккаунте", callback_data="account_info_opt")],
            [types.InlineKeyboardButton(text="Выйти", callback_data="account_logout_opt")],
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu_back")]
        ])
        await callback_query.message.edit_text(f"Аккаунт: {username_db}", reply_markup=account_markup)
    except Exception as e:
        logging.error(f"Error in handle_menu_account: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'main_menu_recommendations')
async def handle_menu_recommendations(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        await callback_query.message.edit_text("Рекомендации:", reply_markup=get_recommendations_menu_markup())
    except Exception as e:
        logging.error(f"Error in handle_menu_recommendations: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()


# --- Поиск: Подменю ---
@dp.callback_query(lambda c: c.data == 'search_tracks_opt')
async def handle_search_tracks_opt(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        await callback_query.message.edit_text("Введите название трека для поиска:")
        await state.set_state(SearchStates.waiting_for_track_query)
    except Exception as e:
        logging.error(f"Error in handle_search_tracks_opt: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()

# --- Поиск: Поиск треков ---
@dp.message(SearchStates.waiting_for_track_query)
async def process_track_search_query(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        await state.set_state(None)
        return

    query = message.text
    user_id_db = user_auth_data.get('user_id_db')
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

                cursor.execute("""
                               SELECT EXISTS (SELECT 1
                                              FROM user_reaction ur_check
                                                       JOIN reactions r_check ON ur_check.reaction_id = r_check.id
                                              WHERE ur_check.user_id = %s
                                                AND ur_check.track_id = %s
                                                AND r_check.type = 'like')
                               """, (user_id_db, tid))
                is_liked = cursor.fetchone()[0]

                buttons = []
                if is_liked:
                    buttons.append(types.InlineKeyboardButton(text="👎 Dislike", callback_data=f"unlike_track_{tid}"))
                else:
                    buttons.append(types.InlineKeyboardButton(text="👍 Like", callback_data=f"like_track_{tid}"))

                if author_id_val:
                    buttons.append(
                        types.InlineKeyboardButton(text="👤 Автор", callback_data=f"view_author_{author_id_val}"))

                markup = types.InlineKeyboardMarkup(inline_keyboard=[buttons])
                await message.answer(track_text, reply_markup=markup)
        else:
            await message.answer("❌ Треки с таким названием не найдены.")
    except psycopg2.Error as db_err:
        logging.error(f"Database error in process_track_search_query: {db_err}")
        await send_error_message(message, "❌ Произошла ошибка при поиске треков (база данных).")
    except Exception as e:
        logging.error(f"Unexpected error in process_track_search_query: {e}")
        await send_error_message(message)
    finally:
        await state.set_state(None)
        await message.answer("Меню поиска:", reply_markup=get_search_menu_markup())


@dp.callback_query(lambda c: c.data == 'search_albums_opt')
async def handle_search_albums_opt(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        await callback_query.message.edit_text("Введите название альбома для поиска:")
        await state.set_state(SearchStates.waiting_for_album_query)
    except Exception as e:
        logging.error(f"Error in handle_search_albums_opt: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()

# --- Поиск: Поиск альбомов ---
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
                buttons = []
                if author_id_val:
                    buttons.append(
                        types.InlineKeyboardButton(text="👤 К автору", callback_data=f"view_author_{author_id_val}"))
                buttons.append(
                    types.InlineKeyboardButton(text="🎼 Треки", callback_data=f"list_tracks_for_album_{aid}"))
                markup = types.InlineKeyboardMarkup(inline_keyboard=[buttons])
                await message.answer(album_text, reply_markup=markup)
        else:
            await message.answer("❌ Альбомы с таким названием не найдены.")
    except psycopg2.Error as db_err:
        logging.error(f"Database error in process_album_search_query: {db_err}")
        await send_error_message(message, "❌ Произошла ошибка при поиске альбомов (база данных).")
    except Exception as e:
        logging.error(f"Unexpected error in process_album_search_query: {e}")
        await send_error_message(message)
    finally:
        await state.set_state(None)
        await message.answer("Меню поиска:", reply_markup=get_search_menu_markup())


@dp.callback_query(lambda c: c.data == 'search_artists_opt')
async def handle_search_artists_opt(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        await callback_query.message.edit_text("Введите имя или часть имени исполнителя для поиска:")
        await state.set_state(SearchStates.waiting_for_artist_query)
    except Exception as e:
        logging.error(f"Error in handle_search_artists_opt: {e}")
        await send_error_message(callback_query)
    finally:
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
                    types.InlineKeyboardButton(text="🛍️ Мерч", callback_data=f"view_merch_{aid}"),
                    types.InlineKeyboardButton(text="🎤 Концерты", callback_data=f"view_concerts_{aid}")
                ]
                markup = types.InlineKeyboardMarkup(inline_keyboard=[buttons])
                await message.answer(artist_text, reply_markup=markup)
        else:
            await message.answer("❌ Исполнители с таким именем не найдены.")
    except psycopg2.Error as db_err:
        logging.error(f"Database error in process_artist_search_query: {db_err}")
        await send_error_message(message, "❌ Произошла ошибка при поиске исполнителей (база данных).")
    except Exception as e:
        logging.error(f"Unexpected error in process_artist_search_query: {e}")
        await send_error_message(message)
    finally:
        await state.set_state(None)
        await message.answer("Меню поиска:", reply_markup=get_search_menu_markup())


# --- Трек: Лайк ---
@dp.callback_query(lambda c: c.data.startswith('like_track_'))
async def handle_like_track(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return

    user_id_db = user_auth_data.get('user_id_db')
    track_id = int(callback_query.data.split('_')[-1])

    try:
        cursor.execute("SELECT id FROM reactions WHERE type = 'like'")
        reaction_like_row = cursor.fetchone()
        if not reaction_like_row:
            await callback_query.answer("❌ Тип реакции 'like' не найден в системе.", show_alert=True)
            return
        reaction_like_id = reaction_like_row[0]

        cursor.execute("SELECT id FROM track WHERE id = %s", (track_id,))
        if not cursor.fetchone():
            await callback_query.answer(f"Трек ID {track_id} не найден.", show_alert=True)
            return

        cursor.execute(
            "INSERT INTO user_reaction (user_id, reaction_id, track_id) VALUES (%s, %s, %s)",
            (user_id_db, reaction_like_id, track_id)
        )
        conn.commit()
        await callback_query.answer(f"Трек ID {track_id} понравился!", show_alert=False)

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        await callback_query.answer("Вы уже лайкнули этот трек.", show_alert=True)
    except psycopg2.Error as db_err:
        conn.rollback()
        logging.error(f"Database error liking track {track_id} for user {user_id_db}: {db_err}")
        await callback_query.answer("Ошибка базы данных при попытке лайкнуть.", show_alert=True)
    except Exception as e:
        conn.rollback()
        logging.error(f"Unexpected error liking track {track_id} for user {user_id_db}: {e}")
        await callback_query.answer("Произошла ошибка.", show_alert=True)


# --- Трек: Дизлайк ---
@dp.callback_query(lambda c: c.data.startswith('unlike_track_'))
async def handle_unlike_track(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return

    user_id_db = user_auth_data.get('user_id_db')
    track_id = int(callback_query.data.split('_')[-1])

    try:
        cursor.execute("SELECT id FROM reactions WHERE type = 'like'")
        reaction_like_row = cursor.fetchone()
        if not reaction_like_row:
            await callback_query.answer("❌ Тип реакции 'like' не найден.", show_alert=True)
            return
        reaction_like_id = reaction_like_row[0]

        cursor.execute(
            "SELECT id FROM user_reaction WHERE user_id = %s AND reaction_id = %s AND track_id = %s",
            (user_id_db, reaction_like_id, track_id)
        )
        if not cursor.fetchone():
            await callback_query.answer("Вы еще не лайкали этот трек, или он уже не понравился.", show_alert=True)
            return

        cursor.execute(
            "DELETE FROM user_reaction WHERE user_id = %s AND reaction_id = %s AND track_id = %s",
            (user_id_db, reaction_like_id, track_id)
        )
        conn.commit()
        if cursor.rowcount > 0:
            await callback_query.answer(f"Трек ID {track_id} больше не нравится.", show_alert=False)
        else:
            await callback_query.answer("Не удалось убрать лайк. Возможно, он уже был убран.", show_alert=True)

    except psycopg2.Error as db_err:
        conn.rollback()
        logging.error(f"Database error unliking track {track_id} for user {user_id_db}: {db_err}")
        await callback_query.answer("Ошибка базы данных при попытке убрать лайк.", show_alert=True)
    except Exception as e:
        conn.rollback()
        logging.error(f"Unexpected error unliking track {track_id} for user {user_id_db}: {e}")
        await callback_query.answer("Произошла ошибка при попытке убрать лайк.", show_alert=True)

# --- Автор ---
@dp.callback_query(lambda c: c.data.startswith('view_author_'))
async def handle_view_author(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        author_id = int(callback_query.data.split('_')[-1])
        cursor.execute("SELECT id, name, auditions, bio FROM author WHERE id = %s", (author_id,))
        author_data = cursor.fetchone()

        if author_data:
            aid, name, auditions, bio = author_data
            text = f"👤 Исполнитель: {name}\nID: {aid}\nПрослушиваний: {auditions if auditions else 0}\nBIO: {bio if bio else 'N/A'}"
            author_actions_markup = types.InlineKeyboardMarkup(inline_keyboard=[
                [
                    types.InlineKeyboardButton(text="🛍️ Мерч", callback_data=f"view_merch_{aid}"),
                    types.InlineKeyboardButton(text="🎤 Концерты", callback_data=f"view_concerts_{aid}")
                ],
                [types.InlineKeyboardButton(text="⬅️ Назад в поиск", callback_data="main_menu_search")]
            ])
            await callback_query.message.answer(text, reply_markup=author_actions_markup)
            await callback_query.answer()
        else:
            await callback_query.message.answer("Информация об исполнителе не найдена.")
            await callback_query.answer()
    except psycopg2.Error as db_err:
        logging.error(f"DB error in handle_view_author: {db_err}")
        await send_error_message(callback_query, "Ошибка при загрузке информации об авторе (база данных).")
    except Exception as e:
        logging.error(f"Error in handle_view_author: {e}")
        await send_error_message(callback_query, "Не удалось загрузить информацию об авторе.")
        await callback_query.answer()

# --- Список треков в альбоме ---
@dp.callback_query(lambda c: c.data.startswith('list_tracks_for_album_'))
async def handle_list_tracks_for_album(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        album_id = int(callback_query.data.split('_')[-1])
        cursor.execute("SELECT title FROM album WHERE id = %s", (album_id,))
        album_title_row = cursor.fetchone()
        if not album_title_row:
            await callback_query.message.answer("Альбом не найден.")
            await callback_query.answer()
            return
        album_title = album_title_row[0]

        cursor.execute(
            """SELECT t.id, t.name, au.name as author_name
               FROM track t
                        LEFT JOIN album al ON t.album_id = al.id
                        LEFT JOIN author au ON al.author_id = au.id
               WHERE t.album_id = %s""", (album_id,))
        tracks = cursor.fetchall()
        if tracks:
            response_text = f"🎶 Треки в альбоме '{album_title}':\n"
            for tid, name, author_name_track in tracks:
                response_text += f"\n- {name} (Исп: {author_name_track if author_name_track else 'N/A'}, ID: {tid})"
        else:
            response_text = f"В альбоме '{album_title}' пока нет треков."
        await callback_query.message.answer(response_text)
    except psycopg2.Error as db_err:
        logging.error(f"DB error in handle_list_tracks_for_album: {db_err}")
        await send_error_message(callback_query, "Ошибка при загрузке треков альбома.")
    except Exception as e:
        logging.error(f"Error in handle_list_tracks_for_album: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()

# --- Мерч ---
@dp.callback_query(lambda c: c.data.startswith('view_merch_'))
async def handle_view_merch(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        author_id = int(callback_query.data.split('_')[-1])
        cursor.execute("SELECT name FROM author WHERE id = %s", (author_id,))
        author_name_row = cursor.fetchone()
        author_name = author_name_row[0] if author_name_row else "Неизвестный исполнитель"

        cursor.execute("SELECT name, price, amount FROM merch WHERE author_id = %s ORDER BY name", (author_id,))
        merch_items = cursor.fetchall()
        if merch_items:
            response_text = f"🛍️ Мерч исполнителя {author_name}:\n"
            for name, price, amount in merch_items:
                response_text += f"\n- {name}\n  Цена: {price} руб., В наличии: {amount if amount > 0 else 'Нет'}"
        else:
            response_text = f"У исполнителя {author_name} пока нет мерча."
        await callback_query.message.answer(response_text)
    except psycopg2.Error as db_err:
        logging.error(f"DB error in handle_view_merch: {db_err}")
        await send_error_message(callback_query, "Ошибка при загрузке мерча (база данных).")
    except Exception as e:
        logging.error(f"Error in handle_view_merch: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()

# --- Концерты ---
@dp.callback_query(lambda c: c.data.startswith('view_concerts_'))
async def handle_view_concerts(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        author_id = int(callback_query.data.split('_')[-1])
        cursor.execute("SELECT name FROM author WHERE id = %s", (author_id,))
        author_name_row = cursor.fetchone()
        author_name = author_name_row[0] if author_name_row else "Неизвестный исполнитель"

        cursor.execute("SELECT price_of_ticket, \"date\", place FROM concerts WHERE author_id = %s ORDER BY \"date\"",
                       (author_id,))
        concert_items = cursor.fetchall()
        if concert_items:
            response_text = f"🎤 Концерты исполнителя {author_name}:\n"
            for price, date_val, place in concert_items:
                formatted_date = date_val.strftime("%d %B %Y, %H:%M") if date_val else "Дата не указана"
                response_text += f"\n- Место: {place}\n  Дата: {formatted_date}\n  Цена билета: {price} руб."
        else:
            response_text = f"У исполнителя {author_name} пока нет запланированных концертов."
        await callback_query.message.answer(response_text)
    except psycopg2.Error as db_err:
        logging.error(f"DB error in handle_view_concerts: {db_err}")
        await send_error_message(callback_query, "Ошибка при загрузке концертов (база данных).")
    except Exception as e:
        logging.error(f"Error in handle_view_concerts: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()


# --- Библиотека: Мои плейлисты ---
@dp.callback_query(lambda c: c.data == 'library_my_playlists')
async def handle_library_my_playlists(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    try:
        await list_my_playlists(callback_query.message, state, is_callback=True)
    except Exception as e:
        logging.error(f"Error in handle_library_my_playlists: {e}")
        await send_error_message(callback_query)
    finally:
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
            await callback_query.message.answer("👍 Понравившиеся треки (до 20):")
            for tid, name, album, author in tracks:
                track_text = f"ID: {tid}. {name} (Альбом: {album if album else 'N/A'}, Исп: {author if author else 'N/A'})"
                markup = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="👎 Dislike", callback_data=f"unlike_track_{tid}")]
                ])
                await callback_query.message.answer(track_text, reply_markup=markup)
        else:
            await callback_query.message.answer("У вас нет понравившихся треков.")
    except psycopg2.Error as db_err:
        logging.error(f"DB error in handle_library_liked_tracks: {db_err}")
        await send_error_message(callback_query, "❌ Ошибка при получении понравившихся треков (база данных).")
    except Exception as e:
        logging.error(f"Unexpected error in handle_library_liked_tracks: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()


# --- Рекомендации: ТОП-10 треков ---
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
    except psycopg2.Error as db_err:
        logging.error(f"DB error in handle_recomm_top_10_tracks: {db_err}")
        await send_error_message(callback_query, "❌ Произошла ошибка при получении топ-10 треков (база данных).")
    except Exception as e:
        logging.error(f"Unexpected error in handle_recomm_top_10_tracks: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()


@dp.callback_query(lambda c: c.data == 'recomm_user_tags')
async def handle_recomm_user_tags(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return

    user_id_db = user_auth_data.get('user_id_db')
    try:
        # Получим теги из треков пользователя
        cursor.execute(
            """SELECT DISTINCT tt.tag_id
               FROM user_reaction ur
                        JOIN reactions react ON ur.reaction_id = react.id
                        JOIN track t ON ur.track_id = t.id
                        JOIN track_tags tt ON t.id = tt.track_id -- UPDATED to track_tags
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

        # Получить рекомендованные треки, основываясь на понравившихся треках
        cursor.execute(
            """SELECT t.id,
                      t.name,
                      COUNT(DISTINCT tt.tag_id) as matching_tags,
                      t.auditions,
                      al.title                  as album_name,
                      au.name                   as author_name
               FROM track t
                        JOIN track_tags tt ON t.id = tt.track_id -- UPDATED to track_tags
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
            response_text = "Не удалось подобрать персональные рекомендации. Возможно, стоит расширить список понравившихся треков или в системе нет подходящих треков."
        await callback_query.message.answer(response_text)
    except psycopg2.Error as db_err:
        conn.rollback()
        logging.error(f"Database error in handle_recomm_user_tags for user {user_id_db}: {db_err}")
        await send_error_message(callback_query, "❌ Произошла ошибка при подборе рекомендаций (база данных).")
    except Exception as e:
        logging.error(f"Unexpected error in handle_recomm_user_tags for user {user_id_db}: {e}")
        await send_error_message(callback_query, "❌ Произошла ошибка при подборе рекомендаций.")
    finally:
        await callback_query.answer()


# --- Мои плейлисты ---
@dp.message(Command("my_playlists"))
async def list_my_playlists(message: types.Message, state: FSMContext, is_callback: bool = False):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data: return

    user_id_db = user_auth_data.get('user_id_db')
    try:
        cursor.execute("SELECT id, title FROM playlist WHERE user_id = %s ORDER BY title", (user_id_db,))
        playlists = cursor.fetchall()

        target_message_object = message
        if is_callback:
            target_message_object = message

        if playlists:
            await target_message_object.answer("📜 Ваши плейлисты:")
            for pid, title in playlists:
                markup = types.InlineKeyboardMarkup(inline_keyboard=[
                    [
                        types.InlineKeyboardButton(text="🎵 Треки", callback_data=f"view_playlist_tracks_{pid}"),
                        types.InlineKeyboardButton(text="🏷️ Теги", callback_data=f"view_playlist_tags_{pid}")
                    ],
                    [
                        types.InlineKeyboardButton(text="➕ Добавить трек сюда",
                                                   callback_data=f"add_track_to_this_playlist_start_{pid}")
                    ]
                ])
                await target_message_object.answer(f"▶️ {title} (ID: {pid})", reply_markup=markup)
        else:
            await target_message_object.answer(
                "У вас нет плейлистов. Создайте новый через меню 'Добавить' или 'Моя Библиотека'.")
    except psycopg2.Error as db_err:
        logging.error(f"DB error in list_my_playlists for user {user_id_db}: {db_err}")
        event_obj = message if not is_callback else types.CallbackQuery(message=message, from_user=message.chat,
                                                                        id="temp_cq_id")  # Create a mock CQ for send_error_message if needed
        await send_error_message(event_obj, "❌ Ошибка при получении списка плейлистов (база данных).")
    except Exception as e:
        logging.error(f"Unexpected error in list_my_playlists for user {user_id_db}: {e}")
        event_obj = message if not is_callback else types.CallbackQuery(message=message, from_user=message.chat,
                                                                        id="temp_cq_id")
        await send_error_message(event_obj)


# --- Обработчик для управления плейлистами ---
@dp.callback_query(lambda c: c.data.startswith('view_playlist_tracks_'))
async def handle_view_playlist_tracks(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return

    playlist_id = int(callback_query.data.split('_')[-1])
    try:
        cursor.execute("SELECT title FROM playlist WHERE id = %s",
                       (playlist_id,))
        playlist_info = cursor.fetchone()
        if not playlist_info:
            await callback_query.message.answer("❌ Плейлист не найден.")
            await callback_query.answer()
            return

        playlist_title = playlist_info[0]

        cursor.execute(
            """SELECT t.id, t.name
               FROM track t
                        JOIN playlist_tracklist ptl ON t.id = ptl.track_id
               WHERE ptl.playlist_id = %s
               ORDER BY t.name""", (playlist_id,)
        )
        tracks = cursor.fetchall()

        if tracks:
            await callback_query.message.answer(f"🎶 Треки в плейлисте '{playlist_title}':")
            for track_id, track_name in tracks:
                buttons = [[types.InlineKeyboardButton(text="➖ Удалить из плейлиста",
                                                       callback_data=f"remove_track_from_playlist_{playlist_id}_{track_id}")]]
                markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)
                await callback_query.message.answer(f"- {track_name} (ID: {track_id})", reply_markup=markup)
        else:
            await callback_query.message.answer(f"🎶 Треки в плейлисте '{playlist_title}':\n\nПлейлист пока пуст.")

        back_button = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⬅️ К моим плейлистам", callback_data="library_my_playlists")]
        ])
        await callback_query.message.answer("Управление треками плейлиста:", reply_markup=back_button)

    except psycopg2.Error as db_err:
        logging.error(f"DB error viewing tracks for playlist {playlist_id}: {db_err}")
        await send_error_message(callback_query, "Ошибка при загрузке треков плейлиста.")
    except Exception as e:
        logging.error(f"Error viewing tracks for playlist {playlist_id}: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()


@dp.callback_query(lambda c: c.data.startswith('view_playlist_tags_'))
async def handle_view_playlist_tags(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return
    playlist_id = int(callback_query.data.split('_')[-1])
    try:
        cursor.execute("SELECT title FROM playlist WHERE id = %s", (playlist_id,))
        playlist_title_row = cursor.fetchone()
        if not playlist_title_row:
            await callback_query.message.answer("❌ Плейлист не найден.")
            await callback_query.answer()
            return
        playlist_title = playlist_title_row[0]

        cursor.execute(
            """SELECT tg.name
               FROM tag tg
                        JOIN playlist_tags pt ON tg.id = pt.tag_id
               WHERE pt.playlist_id = %s""", (playlist_id,))
        tags = cursor.fetchall()
        response_text = f"🏷️ Теги плейлиста '{playlist_title}':\n"
        if tags:
            response_text += "\n".join([f"- {tag[0]}" for tag in tags])
        else:
            response_text += "У этого плейлиста нет тегов."

        back_button = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⬅️ К моим плейлистам", callback_data="library_my_playlists")]
        ])
        await callback_query.message.answer(response_text, reply_markup=back_button)

    except psycopg2.Error as db_err:
        logging.error(f"DB error viewing tags for playlist {playlist_id}: {db_err}")
        await send_error_message(callback_query, "Ошибка при загрузке тегов плейлиста.")
    except Exception as e:
        logging.error(f"Error viewing tags for playlist {playlist_id}: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()


@dp.callback_query(lambda c: c.data.startswith('add_track_to_this_playlist_start_'))
async def handle_add_track_to_this_playlist_start(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return

    playlist_id = int(callback_query.data.split('_')[-1])
    user_id_db = user_auth_data.get('user_id_db')
    try:
        cursor.execute("SELECT title FROM playlist WHERE id = %s AND user_id = %s", (playlist_id, user_id_db))
        playlist_data = cursor.fetchone()
        if not playlist_data:
            await callback_query.message.answer("❌ Плейлист не найден или не принадлежит вам.")
            await callback_query.answer()
            return

        playlist_title = playlist_data[0]
        await state.update_data(playlist_id_to_add_to=playlist_id, playlist_title_to_add_to=playlist_title)
        await callback_query.message.answer(
            f"Добавление трека в плейлист '{playlist_title}'.\nВведите ID или название трека:")
        await state.set_state(PlaylistManagementStates.waiting_for_track_to_add_to_existing_playlist)

    except psycopg2.Error as db_err:
        logging.error(f"DB error starting to add track to playlist {playlist_id}: {db_err}")
        await send_error_message(callback_query, "Ошибка при подготовке к добавлению трека.")
    except Exception as e:
        logging.error(f"Error starting to add track to playlist {playlist_id}: {e}")
        await send_error_message(callback_query)
    finally:
        await callback_query.answer()


@dp.message(PlaylistManagementStates.waiting_for_track_to_add_to_existing_playlist)
async def process_add_track_to_existing_playlist_input(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        await state.clear()
        return

    fsm_data = await state.get_data()
    playlist_id = fsm_data.get('playlist_id_to_add_to')
    playlist_title = fsm_data.get('playlist_title_to_add_to', 'этот плейлист')

    if not playlist_id:
        await message.reply("Произошла ошибка, ID плейлиста не найден. Пожалуйста, выберите плейлист заново.")
        await state.clear()
        return

    track_input = message.text.strip()
    found_track_id = None
    found_track_name = None
    try:
        if track_input.isdigit():
            track_id_candidate = int(track_input)
            cursor.execute("SELECT id, name FROM track WHERE id = %s", (track_id_candidate,))
            track_record = cursor.fetchone()
            if track_record:
                found_track_id, found_track_name = track_record
            else:
                await message.reply(f"Трек с ID {track_id_candidate} не найден. Попробуйте другое ID или название.")
                return
        else:
            cursor.execute("SELECT id, name FROM track WHERE name ILIKE %s", (f'%{track_input}%',))
            tracks_found = cursor.fetchall()
            if not tracks_found:
                await message.reply(
                    f"Трек с названием, похожим на '{track_input}', не найден. Попробуйте другое название или ID.")
                return
            if len(tracks_found) == 1:
                found_track_id, found_track_name = tracks_found[0]
            else:
                response_text = "Найдено несколько треков. Пожалуйста, выберите один, отправив его ID (или /done_adding_to_playlist для завершения):\n"
                for tid, tname in tracks_found[:5]:
                    response_text += f"ID: {tid} - {tname}\n"
                await message.reply(
                    response_text + "\nПожалуйста, введите точный ID выбранного трека или уточните название.")
                return

        if found_track_id and found_track_name:
            cursor.execute(
                "INSERT INTO playlist_tracklist (playlist_id, track_id) VALUES (%s, %s)",
                (playlist_id, found_track_id)
            )
            conn.commit()
            await message.reply(
                f"Трек '{found_track_name}' (ID: {found_track_id}) добавлен в плейлист '{playlist_title}'.\n"
                "Введите следующий трек, или /done_adding_to_playlist для завершения.")
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        await message.reply(f"Трек '{found_track_name}' уже есть в плейлисте '{playlist_title}'. Введите другой.")
    except psycopg2.Error as db_err:
        conn.rollback()
        logging.error(f"DB error adding track to existing playlist {playlist_id}: {db_err}")
        await message.reply("❌ Произошла ошибка при добавлении трека (база данных).")
    except Exception as e:
        conn.rollback()
        logging.error(f"Error adding track to existing playlist {playlist_id}: {e}")
        await message.reply("❌ Произошла ошибка при добавлении трека.")


@dp.message(Command("done_adding_to_playlist"), PlaylistManagementStates.waiting_for_track_to_add_to_existing_playlist)
async def process_done_adding_to_existing_playlist(message: types.Message, state: FSMContext):
    user_auth_data = await ensure_authenticated(message, state)
    if not user_auth_data:
        await state.clear()
        return
    fsm_data = await state.get_data()
    playlist_title = fsm_data.get('playlist_title_to_add_to', 'плейлист')
    await message.answer(f"Завершено добавление треков в '{playlist_title}'.")
    await state.clear()
    await message.answer("Моя библиотека:", reply_markup=(await get_library_menu_markup(state)))


@dp.callback_query(lambda c: c.data.startswith('remove_track_from_playlist_'))
async def handle_remove_track_from_playlist(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data: return

    parts = callback_query.data.split('_')
    playlist_id = int(parts[-2])
    track_id = int(parts[-1])
    user_id_db = user_auth_data.get('user_id_db')

    try:
        cursor.execute("SELECT user_id FROM playlist WHERE id = %s", (playlist_id,))
        owner_id_row = cursor.fetchone()
        if not owner_id_row or owner_id_row[0] != user_id_db:
            await callback_query.answer("❌ Вы не можете изменять этот плейлист.", show_alert=True)
            return

        cursor.execute(
            "DELETE FROM playlist_tracklist WHERE playlist_id = %s AND track_id = %s",
            (playlist_id, track_id)
        )
        conn.commit()
        if cursor.rowcount > 0:
            await callback_query.answer(f"Трек (ID: {track_id}) удален из плейлиста.", show_alert=False)
            await callback_query.message.delete()
        else:
            await callback_query.answer("Трек не найден в плейлисте или уже удален.", show_alert=True)

    except psycopg2.Error as db_err:
        conn.rollback()
        logging.error(f"DB error removing track {track_id} from playlist {playlist_id}: {db_err}")
        await callback_query.answer("Ошибка базы данных при удалении трека.", show_alert=True)
    except Exception as e:
        conn.rollback()
        logging.error(f"Error removing track {track_id} from playlist {playlist_id}: {e}")
        await callback_query.answer("Произошла ошибка при удалении трека.", show_alert=True)


# --- Helper to get library menu (used after some playlist operations) ---
async def get_library_menu_markup(state: FSMContext):
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Мои плейлисты", callback_data="library_my_playlists")],
        [types.InlineKeyboardButton(text="Понравившиеся треки", callback_data="library_liked_tracks")],
        [types.InlineKeyboardButton(text="➕ Создать новый плейлист",
                                    callback_data="create_playlist_interactive_start")],
        [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="main_menu_back")]
    ])


# --- Обработчики для Аккаунта ---
@dp.callback_query(lambda c: c.data == 'account_info_opt')
async def handle_account_info(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data:
        return

    user_id_db = user_auth_data.get('user_id_db')
    username_db = user_auth_data.get('username_db', 'N/A')

    try:
        cursor.execute("SELECT mail FROM \"user\" WHERE id = %s", (user_id_db,))
        user_db_details = cursor.fetchone()

        email = user_db_details[0] if user_db_details and user_db_details[0] else "Не указан"

        info_text = (f"👤 Информация о вашем аккаунте:\n\n"
                     f"🔹 ID: {user_id_db}\n"
                     f"🔹 Username: {username_db}\n"
                     f"🔹 Email: {email}\n"
                     )

        # Отправка сообщения под меню
        await callback_query.message.answer(info_text)
        await callback_query.answer()

    except psycopg2.Error as db_err:
        logging.error(f"Database error in handle_account_info for user {user_id_db}: {db_err}")
        await send_error_message(callback_query, "❌ Ошибка при получении информации об аккаунте (база данных).")
    except Exception as e:
        logging.error(f"Unexpected error in handle_account_info for user {user_id_db}: {e}")
        await send_error_message(callback_query)


@dp.callback_query(lambda c: c.data == 'account_logout_opt')
async def handle_account_logout(callback_query: types.CallbackQuery, state: FSMContext):
    user_auth_data = await ensure_authenticated(callback_query, state)
    if not user_auth_data:
        await callback_query.message.answer("Вы не были авторизованы или ваша сессия уже истекла.")
        await callback_query.answer()
        return

    try:
        username_db = user_auth_data.get('username_db', 'Пользователь')
        await state.clear()

        await callback_query.message.edit_text(f"✅ {username_db}, вы успешно вышли из системы.")

        markup = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Авторизация (Вход)", callback_data="auth_login_start")],
            [types.InlineKeyboardButton(text="Регистрация", callback_data="auth_register_start")]
        ])
        await callback_query.message.answer(
            "Вы можете войти снова или зарегистрировать новый аккаунт.",
            reply_markup=markup
        )
        await callback_query.answer("Выход выполнен")

    except Exception as e:
        logging.error(f"Unexpected error in handle_account_logout: {e}")
        await state.clear()  # Try to clear state even on error
        await send_error_message(callback_query, "❌ Произошла ошибка при выходе из системы.")
        # await callback_query.answer() # Redundant if send_error_message answers


# --- Запуск бота ---
async def main():
    if not conn or not cursor:
        logging.critical("Не удалось подключиться к базе данных. Запуск бота невозможен.")
        return

    logging.info("Starting bot polling...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.critical(f"Bot polling failed critically: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        logging.info("Database connection closed.")


if __name__ == '__main__':
    asyncio.run(main())