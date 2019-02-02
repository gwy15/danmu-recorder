import struct
import json
import asyncio
import time
import datetime

from collections import namedtuple
from enum import IntEnum

import websockets
import requests

from bilive import Danmu


class DanmuOperation(IntEnum):
    SEND_HEARTBEAT = 2
    POPULARITY = 3
    COMMAND = 5
    AUTH = 7
    RECV_HEARTBEAT = 8


HeaderTuple = namedtuple(
    'HeaderTuple', ('total_len', 'header_len', 'proto_ver', 'operation', 'sequence'))


class LiveRoomConnection():
    URL = 'wss://broadcastlv.chat.bilibili.com:2245/sub'
    HEADER_STRUCT = struct.Struct('>I2H2I')

    def __init__(self, room_id, queue):
        super().__init__()
        self.shortId = room_id
        self.queue = queue

        self.roomId = requests.get(
            'https://api.live.bilibili.com/room/v1/Room/room_init',
            {'id': room_id}).json()['data']['room_id']

        self._stopFlag = False

    def _make_packet(self, data, operation):
        body = json.dumps(data).encode('utf-8')
        header = self.HEADER_STRUCT.pack(
            self.HEADER_STRUCT.size + len(body),
            self.HEADER_STRUCT.size,
            1,
            operation,
            1
        )
        return header + body

    async def enterRoom(self, ws):
        authParams = {
            'uid':       0,  # 未登录
            'roomid':    self.roomId,
            'protover':  1,
            'platform':  'web',
            'clientver': '1.4.0'
        }
        print(f'entering room {self.shortId}.')
        return await ws.send(self._make_packet(
            authParams, DanmuOperation.AUTH
        ))

    async def onWsMsg(self, ws, message):
        offset = 0
        while offset < len(message):
            try:
                header = HeaderTuple(
                    *self.HEADER_STRUCT.unpack_from(message, offset))
            except struct.error:
                break

            if header.operation == DanmuOperation.RECV_HEARTBEAT:
                await ws.send(self._make_packet({}, DanmuOperation.SEND_HEARTBEAT))

            elif header.operation == DanmuOperation.COMMAND:
                body = message[offset + self.HEADER_STRUCT.size:
                               offset + header.total_len]
                body = json.loads(body.decode('utf-8'))
                await self._handle_command(body)

            offset += header.total_len

    async def _handle_command(self, command):
        if isinstance(command, list):
            for item in command:
                await self._handle_command(item)
            return

        cmd = command['cmd']
        if cmd != 'DANMU_MSG':
            return

        info = command['info']
        danmu = Danmu.fromInfo(info, self.shortId)
        self.queue.put(danmu)

    async def getMainLoop(self):
        while True:
            if self._stopFlag:
                break

            async with websockets.connect(self.URL, ssl=True) as ws:
                await self.enterRoom(ws)
                aws = [
                    self.getMsgLoop(ws),
                    self.getHBLoop(ws)
                ]
                self.gather = asyncio.gather(*aws, return_exceptions=False)

                try:
                    await self.gather
                except websockets.exceptions.ConnectionClosed:
                    print(f'[WARNING] Connection Closed for room {self.shortId}!')
                    self.gather.cancel()
                    continue

    async def getHBLoop(self, ws):
        t = time.time()
        while True:
            if time.time() > t + 30:
                tstr = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f'room {self.shortId} sending heart beat @ {tstr}')
                await ws.send(self._make_packet({}, DanmuOperation.SEND_HEARTBEAT))
                t = time.time()

            await asyncio.sleep(1)
            if self._stopFlag:
                break

    async def getMsgLoop(self, ws):
        async for msg in ws:
            await self.onWsMsg(ws, msg)

            if self._stopFlag:
                break

    async def stop(self):
        self._stopFlag = True
        await asyncio.sleep(3)
        print(f'room {self.shortId} closed!')
