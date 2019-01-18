# -*- coding: utf-8 -*-

import sys
import asyncio
from ssl import SSLError
import logging
import signal
import re
import json

from bilive import BLiveClient, Danmu, DataBase


class MyBLiveClient(BLiveClient):
    def __init__(self, room_id, ssl=True, loop=None, loggerLevel=logging.INFO, db=None):
        super().__init__(room_id, ssl=ssl, loop=loop, loggerLevel=loggerLevel)
        self.db = db

    async def _on_get_danmaku(self, info):
        danmu = Danmu.fromInfo(info, self._short_id)
        self.db.insert(danmu)
        self.logger.debug(
            f'{self._short_id:-6d} UL{danmu.UL:-2d} {danmu.uname}({danmu.uid}): {danmu.msg}')

    def _on_stop(self, exc):
        self._loop.stop()

    def _handle_error(self, exc):
        self.logger.warning(exc)
        if isinstance(exc, SSLError):
            self.logger.error('SSL验证失败！')
        return False


clients = []


def ask_exit():
    for task in asyncio.Task.all_tasks():
        task.cancel()
    for client in clients:
        client.stop()


def main():
    with open('./config.json', 'r', encoding='utf8') as f:
        conf = json.load(f)
    room_ids = conf['room_ids']
    db = DataBase(conf['DB_PATH'])

    loop = asyncio.get_event_loop()

    for room_id in room_ids:
        client = MyBLiveClient(room_id=room_id, ssl=True, loop=None,
                               loggerLevel=logging.INFO, db=db)
        client.start()
        clients.append(client)

    signal.signal(signal.SIGINT, lambda a, b: ask_exit())

    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


if __name__ == '__main__':
    main()
