from enum import IntEnum
import asyncio
import time
import json

from multiprocessing import Process, Queue
import queue

from bilive import LiveRoomConnection
from bilive import DataBase


class LiveProcess(Process):
    def __init__(self, cmd_queue, data_queue):
        super().__init__()
        self.cmd_queue = cmd_queue
        self.data_queue = data_queue

    def run(self):
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self.main())
        self.loop.close()

    async def main(self):
        self.watchList = {}

        while True:
            try:
                item = self.cmd_queue.get(block=False)
                tasks = []
                for id, con in self.watchList.items():
                    tasks.append(self.loop.create_task(con.stop()))
                for task in tasks:
                    await task
                self.data_queue.put(None)
                break
            except queue.Empty:
                await self.checkRooms()
                await asyncio.sleep(1)

    async def checkRooms(self):
        with open('rooms.json') as f:
            room_ids = json.load(f)
        for id in room_ids:
            if id not in self.watchList:
                self.enterRoom(id)
        for id in list(self.watchList.keys()):
            if id not in room_ids:
                await self.exitRoom(id)

    def enterRoom(self, room_id):
        if room_id in self.watchList:
            return
        con = LiveRoomConnection(room_id, self.data_queue)
        self.watchList[room_id] = con
        self.loop.create_task(con.getMainLoop())

    async def exitRoom(self, room_id):
        if room_id not in self.watchList:
            return
        con = self.watchList[room_id]
        await con.stop()
        del self.watchList[room_id]


class WriteProcess(Process):
    def __init__(self, queue, db_path):
        super().__init__()
        self.queue = queue
        self.db_path = db_path

    def run(self):
        db = DataBase(self.db_path)
        while True:
            danmu = self.queue.get()
            if danmu is None:
                break
            db.insert(danmu)


def main():
    data_queue = Queue()
    cmd_queue = Queue()

    liveProcess = LiveProcess(cmd_queue, data_queue)
    liveProcess.start()

    with open('config.json') as f:
        conf = json.load(f)
    path = conf[conf['DB_PATH']]
    writeProcess = WriteProcess(data_queue, path)
    writeProcess.start()

    while True:
        try:
            time.sleep(10)
        except KeyboardInterrupt:
            cmd_queue.put(None)
            break


if __name__ == "__main__":
    main()
