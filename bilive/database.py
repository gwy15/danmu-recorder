import sqlalchemy

from bilive.danmu import Base, Danmu

class DataBase:
    def __init__(self, db_path='sqlite:///danmu.db'):
        engine = sqlalchemy.create_engine(db_path)
        Base.metadata.create_all(engine)
        sessionMaker = sqlalchemy.orm.sessionmaker(bind=engine)
        self.session = sessionMaker()

    def insert(self, danmu):
        self.session.add(danmu)
        self.session.commit()

if __name__ == "__main__":
    info = [
        [0, 1, 25, 16777215, 1547514256, 1322147806, 0, '3b62d0bd', 0, 0, 0],
        '窝丢，叔叔心态还能蹦？',
        [16655050, '酥脆薯塔', 0, 0, 0, 10000, 1, ''],
        [7, '卿言', '叶落莫言', 280446, 5805790, ''],
        [40, 0, 10512625, 15426],
        ['title-144-2', 'title-144-2'],
        0, 0, None]
    db = DataBase('sqlite:///:memory:')
    danmu = Danmu.fromInfo(info, 387)
    db.insert(danmu)

    records = db.session.query(Danmu).filter().all()
    assert(danmu == records[0])
