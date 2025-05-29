import logging
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
import asyncio

API_TOKEN = '8162663853:AAHasVnLHU5bkyWVAHlWZxGXNy2uNn-O58w'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

conn = psycopg2.connect(dbname="Music service", user="user1", password="12345678", host="localhost")
cursor = conn.cursor()

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.reply("🎵 Добро пожаловать в музыкальный сервис!")

@dp.message(Command("create_playlist"))
async def create_playlist(message: types.Message):
    user_id = message.from_user.id
    title = message.get_args()
    cursor.execute("INSERT INTO playlist (title, cover, user_id) VALUES (%s, %s, %s)", (title, '', user_id))
    conn.commit()
    await message.reply("✅ Плейлист создан.")

@dp.message(Command("my_playlists"))
async def list_playlists(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("SELECT id, title FROM playlist WHERE user_id = %s", (user_id,))
    rows = cursor.fetchall()
    if rows:
        text = "\n".join([f"{id}. {title}" for id, title in rows])
    else:
        text = "У вас нет плейлистов."
    await message.reply(text)

@dp.message(Command("rename_playlist"))
async def rename_playlist(message: types.Message):
    args = message.get_args().split()
    if len(args) < 2:
        return await message.reply("❌ Использование: /rename_playlist <id> <новое_название>")
    playlist_id, new_title = args[0], " ".join(args[1:])
    cursor.execute("UPDATE playlist SET title = %s WHERE id = %s", (new_title, playlist_id))
    conn.commit()
    await message.reply("✅ Название обновлено.")

@dp.message(Command("delete_playlist"))
async def delete_playlist(message: types.Message):
    playlist_id = message.get_args()
    cursor.execute("DELETE FROM playlist WHERE id = %s", (playlist_id,))
    conn.commit()
    await message.reply("🗑 Плейлист удалён.")

@dp.message(Command("add_track"))
async def add_track(message: types.Message):
    args = message.get_args().split(maxsplit=1)
    if len(args) != 2:
        return await message.reply("❌ Использование: /add_track <название> <album_id>")
    name, album_id = args
    cursor.execute("INSERT INTO track (name, auditions, mp3, playlist_id, tag_id, album_id) VALUES (%s, %s, %s, %s, %s, %s)", 
                   (name, 0, '', 1, 1, album_id))
    conn.commit()
    await message.reply("✅ Трек добавлен.")

@dp.message(Command("list_tracks"))
async def list_tracks(message: types.Message):
    cursor.execute("SELECT id, name FROM track LIMIT 20")
    tracks = cursor.fetchall()
    if tracks:
        text = "\n".join([f"{id}. {name}" for id, name in tracks])
    else:
        text = "Нет доступных треков."
    await message.reply(text)

@dp.message(Command("top_genres"))
async def top_genres(message: types.Message):
    cursor.execute("""        SELECT g.name, SUM(t.auditions) AS total
        FROM track t
        JOIN album a ON t.album_id = a.id
        JOIN genre g ON a.genre_id = g.id
        GROUP BY g.name
        ORDER BY total DESC
        LIMIT 5;
    """)
    rows = cursor.fetchall()
    text = "\n".join([f"{name}: {count} прослушиваний" for name, count in rows])
    await message.reply(text)

@dp.message(Command("top_likers"))
async def top_likers(message: types.Message):
    cursor.execute("""        SELECT u.username, COUNT(*) AS likes
        FROM user_reaction ur
        JOIN "user" u ON ur.user_id = u.id
        JOIN reactions r ON ur.reaction_id = r.id
        WHERE r.type = 'like'
        GROUP BY u.username
        HAVING COUNT(*) > 3;
    """)
    rows = cursor.fetchall()
    if rows:
        text = "\n".join([f"{name}: {likes} лайков" for name, likes in rows])
    else:
        text = "Нет пользователей с > 3 лайками."
    await message.reply(text)

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
