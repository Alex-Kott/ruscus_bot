import asyncio
import logging
from asyncio import AbstractEventLoop
from enum import Enum
from datetime import datetime, timedelta
from threading import Thread
from typing import Tuple
from uuid import uuid4

import aiomysql
from aiomysql.connection import Connection as MySQLConnection
from aiogram import Bot, Dispatcher, executor
from aiogram.types.message import ContentType, Message, ParseMode
from aiogram.utils.exceptions import MessageToDeleteNotFound, MessageCantBeDeleted

from config import BOT_TOKEN, MYSQL_DB_HOST, MYSQL_DB_NAME, MYSQL_DB_PASSWORD, MYSQL_DB_USERNAME, REMOVING_DELAY
from models import ActionScheduler, User


logging.basicConfig(level=logging.ERROR,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='./logs/log')
logger = logging.getLogger('ruscus')
logger.setLevel(logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)


class Actions(Enum):
    REMOVE = 'remove'


def init_tables():
    ActionScheduler.create_table(fail_silently=True)
    User.create_table(fail_silently=True)


async def get_mysql_connection() -> MySQLConnection:
    return await aiomysql.connect(host=MYSQL_DB_HOST,
                                  db=MYSQL_DB_NAME,
                                  user=MYSQL_DB_USERNAME,
                                  password=MYSQL_DB_PASSWORD)


@dp.message_handler(content_types=[ContentType.PHOTO, ContentType.AUDIO, ContentType.STICKER, ContentType.VIDEO,
                                   ContentType.VIDEO_NOTE, ContentType.VOICE])
async def set_deletion_timer(message: Message) -> None:
    deletion_timer = ActionScheduler(action=Actions.REMOVE.value,
                                     datetime=datetime.now() + timedelta(seconds=REMOVING_DELAY),
                                     chat_id=message.chat.id,
                                     message_id=message.message_id)
    deletion_timer.save()


@dp.message_handler(commands=['start'])
async def start(message: Message):
    User.cog(message['from'])
    await message.reply('Welcome. You can send /auth-command or /check your authorization.')


@dp.message_handler(commands=['auth'])
async def get_token(message: Message):
    user = User.cog(message['from'])
    user.auth_token = uuid4()
    user.save()

    await message.reply(f'Your authentication token is \n```{user.auth_token}```', parse_mode=ParseMode.MARKDOWN)


@dp.message_handler(commands=['check'])
async def check_token(message: Message):
    user = User.cog(message['from'])
    mysql_conn = await get_mysql_connection()
    async with mysql_conn.cursor() as cur:
        await cur.execute(f"SELECT * FROM wp_comments WHERE comment_content LIKE '%{user.auth_token}%'")
        if await cur.fetchone() is None:
            await message.reply(f"Authenticated token was not found in comments. "
                                f"Please, make sure you posted your token on site or contact admin: admin@site.com")
        else:
            user.auth = True
            user.save()
            await message.reply(f"Authenticated success.")

    mysql_conn.close()


class ThreadRunner(Thread):
    def __init__(self, bot: Bot, loop: AbstractEventLoop):
        super().__init__()
        self.bot = bot
        self.loop = loop

    async def main(self):
        while True:
            tasks = []
            for action in ActionScheduler.select().where(ActionScheduler.datetime < datetime.now()):
                task = self.delete_message(action.chat_id, action.message_id)
                tasks.append(task)
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):  # бывает и такое  ¯\_(ツ)_/¯
                    continue
                else:
                    action = ActionScheduler.get(ActionScheduler.chat_id == result[0],
                                                 ActionScheduler.message_id == result[1])
                    action.delete_instance()
            await asyncio.sleep(1)

    @staticmethod
    async def delete_message(chat_id: int, msg_id: int) -> Tuple[int, int]:
        try:
            await bot.delete_message(chat_id, msg_id)
        except MessageToDeleteNotFound as e:
            logging.exception('Message to delete not found')
        except MessageCantBeDeleted as e:
            logging.exception("Message can't be deleted")
        except Exception as e:
            logging.exception('Something went wrong')
            raise e

        return chat_id, msg_id

    def run(self):
        self.loop.create_task(self.main())


if __name__ == '__main__':
    init_tables()
    event_loop = asyncio.get_event_loop()
    watcher = ThreadRunner(bot=bot, loop=event_loop)
    watcher.daemon = True
    watcher.start()
    executor.start_polling(dp, skip_updates=False)
    event_loop.close()
