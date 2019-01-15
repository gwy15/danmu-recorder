# -*- coding: utf-8 -*-

import json
import struct
import sys
from asyncio import get_event_loop, gather, sleep, CancelledError
from collections import namedtuple
from enum import IntEnum
# noinspection PyProtectedMember
from ssl import _create_unverified_context
import logging

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed


class Operation(IntEnum):
    SEND_HEARTBEAT = 2
    POPULARITY = 3
    COMMAND = 5
    AUTH = 7
    RECV_HEARTBEAT = 8


class BLiveClient:
    ROOM_INIT_URL = 'https://api.live.bilibili.com/room/v1/Room/room_init'
    WEBSOCKET_URL = 'wss://broadcastlv.chat.bilibili.com:2245/sub'

    HEADER_STRUCT = struct.Struct('>I2H2I')
    HeaderTuple = namedtuple(
        'HeaderTuple', ('total_len', 'header_len', 'proto_ver', 'operation', 'sequence'))

    def __init__(self, room_id, ssl=True, loop=None, loggerLevel=logging.INFO):
        """
        :param room_id: URL中的房间ID
        :param ssl: True表示用默认的SSLContext验证，False表示不验证，也可以传入SSLContext
        :param loop: 协程事件循环
        """
        self._short_id = room_id
        self._room_id = None
        # 未登录
        self._uid = 0

        self._ssl = ssl if ssl else _create_unverified_context()
        self._websocket = None

        self._loop = loop or get_event_loop()
        self._future = None

        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '(%(asctime)s) [%(levelname)s] - %(message)s',
                datefmt='%y-%m-%d %H:%M:%S'))
            self.logger.addHandler(handler)
            self.logger.setLevel(loggerLevel)
            self.logger.debug('init complete.')

    def start(self):
        """
        创建相关的协程，不会执行事件循环
        :return: True 表示成功创建协程，False 表示之前创建的协程未结束
        """
        if self._future is not None:
            return False
        self._future = gather(
            self._message_loop(),
            self._heartbeat_loop(),
            loop=self._loop
        )
        self._future.add_done_callback(self.__on_done)
        return True

    def stop(self):
        """
        取消相关的协程，不会停止事件循环
        """
        if self._future is not None:
            self._future.cancel()

    def __on_done(self, future):
        self._future = None
        self._on_stop(future.exception())

    async def _get_room_id(self):
        try:
            async with aiohttp.ClientSession(loop=self._loop) as session:
                async with session.get(self.ROOM_INIT_URL,
                                       params={'id': self._short_id},
                                       ssl=self._ssl) as res:
                    if res.status != 200:
                        raise ConnectionAbortedError('获取房间ID失败：' + res.reason)
                    data = await res.json()
                    if data['code'] != 0:
                        raise ConnectionAbortedError('获取房间ID失败：' + data['msg'])
                    self._room_id = data['data']['room_id']
                    self.logger.debug(f'获取真实房间ID: {self._room_id}')

        except Exception as e:
            if not self._handle_error(e):
                self._future.cancel()
                raise

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

    async def _send_auth(self):
        auth_params = {
            'uid':       self._uid,
            'roomid':    self._room_id,
            'protover':  1,
            'platform':  'web',
            'clientver': '1.4.0'
        }
        await self._websocket.send(self._make_packet(auth_params, Operation.AUTH))

    async def _message_loop(self):
        # 获取房间ID
        if self._room_id is None:
            await self._get_room_id()
            self.logger.info(f'进入房间 {self._room_id}({self._short_id})')

        while True:
            try:
                # 连接
                async with websockets.connect(self.WEBSOCKET_URL,
                                              ssl=self._ssl,
                                              loop=self._loop) as websocket:
                    self._websocket = websocket
                    await self._send_auth()

                    # 处理消息
                    async for message in websocket:
                        await self._handle_message(message)

            except CancelledError:
                self.logger.debug('Cancel...')
                break

            except ConnectionClosed:
                self._websocket = None
                # 重连
                self.logger.warning('掉线重连中')
                try:
                    await sleep(5)
                except CancelledError:
                    break
                continue

            except Exception as e:
                if not self._handle_error(e):
                    self._future.cancel()
                import traceback
                traceback.print_exc()
                raise

            finally:
                self._websocket = None

    async def _heartbeat_loop(self):
        while True:
            try:
                if self._websocket is None:
                    await sleep(0.5)
                else:
                    await self._websocket.send(self._make_packet({}, Operation.SEND_HEARTBEAT))
                    await sleep(30)

            except CancelledError:
                self.logger.debug('Cancel...')
                break
            except ConnectionClosed:
                # 等待重连
                continue
            except Exception as e:
                if not self._handle_error(e):
                    self._future.cancel()
                    raise
                continue

    async def _handle_message(self, message):
        offset = 0
        while offset < len(message):
            try:
                header = self.HeaderTuple(
                    *self.HEADER_STRUCT.unpack_from(message, offset))
            except struct.error:
                break

            if header.operation == Operation.POPULARITY:
                popularity = int.from_bytes(message[offset + self.HEADER_STRUCT.size:
                                                    offset + self.HEADER_STRUCT.size + 4],
                                            'big')
                await self._on_get_popularity(popularity)

            elif header.operation == Operation.COMMAND:
                body = message[offset +
                               self.HEADER_STRUCT.size: offset + header.total_len]
                body = json.loads(body.decode('utf-8'))
                await self._handle_command(body)

            elif header.operation == Operation.RECV_HEARTBEAT:
                await self._websocket.send(self._make_packet({}, Operation.SEND_HEARTBEAT))

            else:
                body = message[offset + self.HEADER_STRUCT.size:
                               offset + header.total_len]
                self.logger.debug('未知包类型: ' + header + ' ' + body)

            offset += header.total_len

    async def _handle_command(self, command):
        if isinstance(command, list):
            for one_command in command:
                await self._handle_command(one_command)
            return

        cmd = command['cmd']
        # self.logger.debug(f'command: {json.dumps(command, indent=2, ensure_ascii=False)}')

        rules = {
            'DANMU_MSG': lambda: self._on_get_danmaku(command['info']),
            'SEND_GIFT': None,
            'WELCOME': None,
            'WELCOME_GUARD': None,
            'SYS_MSG': lambda: self._on_sys_msg(command),
            'WISH_BOTTLE': None,
            'ROOM_RANK': None,
            'ENTRY_EFFECT': None,
            'COMBO_SEND': None,
            'COMBO_END': None,
            'GUARD_MSG': None,  # 开通舰长
            'GUARD_LOTTERY_START': None,
            'GUARD_BUY': None,
            'SPECIAL_GIFT': None,
            'RAFFLE_START': None,
            'ROOM_BLOCK_MSG': lambda: self._on_block_user(command)
        }

        async def default_rule():
            self.logger.info(f'未知命令: {cmd}')

        func = rules.get(cmd, default_rule)
        if func:
            await func()

    async def _on_get_popularity(self, popularity):
        """
        获取到人气值
        :param popularity: 人气值
        """
        pass

    async def _on_get_danmaku(self, info):
        """
        获取到弹幕
        :param info: 弹幕信息
        """
        pass

    def _on_stop(self, exc):
        """
        协程结束后被调用
        :param exc: 如果是异常结束则为异常，否则为None
        """
        pass

    def _handle_error(self, exc):
        """
        处理异常时被调用
        :param exc: 异常
        :return: True表示异常被处理，False表示异常没被处理
        """
        return False

    async def _on_sys_msg(self, command):
        pass

    async def _on_block_user(self, command):
        pass
