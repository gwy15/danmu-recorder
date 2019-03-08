import datetime
import json
from multiprocessing.dummy import Pool
from dataclasses import dataclass

import flask
from flask_bootstrap import Bootstrap
from flask_moment import Moment
from flask_restful import Resource, Api
import requests
from bs4 import BeautifulSoup as bs

from bilive import Danmu, DataBase


class RoomResource(Resource):
    def delete(self, room_id):
        with open('rooms.json') as f:
            rooms = json.load(f)
        if room_id in rooms:
            flask.flash(f'房间号 {room_id} 已删除。', 'success')
            rooms.remove(room_id)
            with open('rooms.json', 'w') as f:
                json.dump(rooms, f)
        else:
            flash.flash(f'房间号 {room_id} 不存在。', 'danger')
        return {'room_id': room_id}

    def post(self, room_id):
        if not (0 < room_id):
            flask.flash('Wrong room id: {}'.format(room_id), 'danger')
            return flask.jsonify({})

        # verify
        if getResponseForRoomId(room_id).status_code == 404:
            flask.flash(f'房间号 {room_id} 不存在!', 'danger')
            return flask.jsonify({})

        with open('rooms.json') as f:
            rooms = json.load(f)
        if not room_id in rooms:
            rooms.append(room_id)
            with open('rooms.json', 'w') as f:
                json.dump(rooms, f)
            flask.flash(f'房间号 {room_id} 已加入监控。', 'success')
        else:
            flask.flash(f'房间号 {room_id} 已存在监控列表中。', 'info')
        return flask.jsonify({})


@dataclass
class Room():
    id: int
    host: str
    title: str
    lastTime: datetime.datetime


def getApp():
    app = flask.Flask(__name__)
    app.config.from_json('config.json')

    Bootstrap().init_app(app)
    Moment(app)
    api = Api(app)
    api.add_resource(RoomResource, '/room/<int:room_id>')

    return app


app = getApp()


def getUrl(url, domain):
    return requests.get(
        url,
        headers={
            'Host': domain,
            'Referer': f'https://{domain}/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.98 Safari/537.36'}
    )


def getResponseForRoomId(room_id):
    return getUrl(f'https://live.bilibili.com/{room_id}', domain='live.bilibili.com')


def getRoom(room_id):
    try:
        web = getResponseForRoomId(room_id).content.decode('utf8')
        soup = bs(web, 'html.parser')
        desc = soup.find('meta', {'name': 'keywords'})['content']
        soup = soup.find('div', {'class': 'script-requirement'}).script
        data = json.loads(soup.text.replace(
            'window.__NEPTUNE_IS_MY_WAIFU__=', ''))
        uid = data['roomInitRes']['data']['uid']
        title = data['baseInfoRes']['data']['title']

        res = getUrl(f'https://api.bilibili.com/x/space/acc/info?mid={uid}',
                     domain='api.bilibili.com')
        host = res.json()['data']['name']

    except Exception as ex:
        host = '发生错误'
        title = str(ex)

    return Room(id=room_id, host=host, title=title, lastTime=None)


@app.route('/admin')
def admin():
    with open('rooms.json') as f:
        roomids = json.load(f)

    with Pool(max(len(roomids), 1)) as pool:
        rooms = pool.map(getRoom, roomids)

    db = DataBase(app.config[app.config['DB_PATH']])
    for room in rooms:
        record = db.session.query(Danmu)\
            .filter(Danmu.room_id == room.id)\
            .order_by(Danmu.time.desc())\
            .first()
        if record is not None:
            room.lastTime = record.time

    rooms = sorted(rooms, key=lambda r: r.id)

    return flask.render_template('admin.html',
                                 rooms=rooms)


@app.route('/')
def index():
    limit = flask.request.args.get('limit', 10, type=int)
    room_id = flask.request.args.get('room_id', None, type=int)
    uname = flask.request.args.get('uname', None, type=str)
    regexp = flask.request.args.get('regexp', None, type=str)
    start_date = flask.request.args.get('start_date', None, type=str)
    end_date = flask.request.args.get('end_date', None, type=str)
    days_limit = flask.request.args.get('days_limit', None, type=int)

    db = DataBase(app.config[app.config['DB_PATH']])

    # total num
    total_num = db.session.query(Danmu).count()

    # time info
    time_info = [[int(dec), cnt] for dec, cnt in
                 db.session.execute('''
        SELECT UNIX_TIMESTAMP(avg(time)) as t, COUNT(*) FROM danmu_records
        WHERE time > utc_timestamp() - INTERVAL 24 HOUR
        GROUP BY UNIX_TIMESTAMP(time) DIV 60
        ORDER BY t DESC;
    ''').fetchall()]  # last 24 hours

    # recent danmus
    query = db.session.query(Danmu)
    if room_id:
        query = query.filter(Danmu.room_id == room_id)
    if uname:
        query = query.filter(Danmu.uname == uname)
    if start_date:
        _start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        query = query.filter(Danmu.time >= _start_date)
    if end_date:
        _end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        query = query.filter(Danmu.time <= _end_date)
    if days_limit:
        _days_limit = datetime.datetime.now() - datetime.timedelta(days=days_limit)
        query = query.filter(Danmu.time >= _days_limit)
    if regexp:
        query = query.filter(Danmu.msg.op('regexp')(regexp))
    danmus = query.order_by(Danmu.time.desc()).limit(limit).all()

    return flask.render_template(
        'index.html',
        danmus=danmus, total_num=total_num,
        time_info=json.dumps(time_info))


if __name__ == "__main__":
    app.run('127.0.0.1', 8888,
            debug=True, threaded=True)
