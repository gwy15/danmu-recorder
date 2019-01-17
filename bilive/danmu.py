import datetime

import sqlalchemy
from sqlalchemy import Column
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects import mysql

Base = declarative_base()


class Danmu(Base):
    # 表的名字:
    __tablename__ = 'danmu_records'

    id = Column(sqlalchemy.Integer, autoincrement=True, primary_key=True)
    room_id = Column(sqlalchemy.Integer, nullable=False, index=True)
    time = Column(mysql.TIMESTAMP(fsp=3), nullable=False, index=True)

    # danmu info
    fontsize = Column(sqlalchemy.SmallInteger, nullable=False)
    color = Column(sqlalchemy.Integer, nullable=False)

    # msg
    msg = Column(sqlalchemy.VARCHAR(128), nullable=False)

    # userinfo
    uid = Column(sqlalchemy.INTEGER, nullable=False)
    uname = Column(sqlalchemy.VARCHAR(64), nullable=False)
    isAdmin = Column(sqlalchemy.Boolean, nullable=False)
    isVIP = Column(sqlalchemy.Boolean, nullable=False)

    # badge
    badgeLevel = Column(sqlalchemy.SmallInteger)
    badgeText = Column(sqlalchemy.VARCHAR(32))
    badgeHostName = Column(sqlalchemy.VARCHAR(64))
    badgeHostRoomId = Column(sqlalchemy.Integer)

    # UL
    UL = Column(sqlalchemy.SmallInteger, nullable=False)

    @staticmethod
    def fromInfo(info, room_id):
        danmuInfo, msg, userInfo, badgeInfo, ULInfo, _1, _2, _3, uNameInfo = info
        _, _, fontsize, color, *_ = danmuInfo
        uid, uname, isAdmin, isVIP, *_ = userInfo
        if badgeInfo:
            badgeLevel, badgeText, badgeHostName, badgeHostRoomId, *_ = badgeInfo
        else:
            badgeLevel, badgeText, badgeHostName, badgeHostRoomId = None, None, None, None
        UL, *_ = ULInfo
        return Danmu(
            time=datetime.datetime.now(), room_id=room_id,
            fontsize=fontsize, color=color,
            msg=msg,
            uid=uid, uname=uname, isAdmin=isAdmin, isVIP=isVIP,
            badgeLevel=badgeLevel, badgeText=badgeText, badgeHostName=badgeHostName, badgeHostRoomId=badgeHostRoomId,
            UL=UL)

    def copy(self):
        dic = {
            k: v
            for k, v in self.__dict__.items()
            if not k.startswith('_')}
        return Danmu(**dic)
