import datetime
import json

import flask
from flask_bootstrap import Bootstrap
from flask_moment import Moment

from bilive import Danmu, DataBase


def getApp():
    app = flask.Flask(__name__)
    Bootstrap().init_app(app)
    Moment(app)
    app.config.from_json('config.json')
    return app


app = getApp()


@app.route('/')
def status():
    limit = flask.request.args.get('limit', 10, type=int)
    room_id = flask.request.args.get('room_id', None, type=int)
    uname = flask.request.args.get('uname', None, type=str)
    regexp = flask.request.args.get('regexp', None, type=str)
    start_date = flask.request.args.get('start_date', None, type=str)
    end_date = flask.request.args.get('end_date', None, type=str)
    days_limit = flask.request.args.get('days_limit', None, type=int)

    db = DataBase(app.config['DB_PATH'])

    # total num
    total_num = db.session.query(Danmu).count()

    # time info
    time_info = [list(item) for item in db.session.execute('''
        SELECT DATE_FORMAT(MAX(time), "%Y-%m-%d %H:%i:00") as t, COUNT(*) FROM bilibili.danmu_records
        WHERE time > utc_timestamp() - INTERVAL 24 HOUR
        GROUP BY UNIX_TIMESTAMP(time) DIV 60
        ORDER BY t DESC;
    ''').fetchall()] # last 24 hours

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
    for danmu in danmus: # convert to utc time
        danmu.time -= datetime.timedelta(hours=8) # 8 as the db timezone is +8

    return flask.render_template(
        'status.html',
        danmus=danmus, total_num=total_num,
        time_info=json.dumps(time_info))


if __name__ == "__main__":
    app.run('127.0.0.1', 8888,
            debug=True, threaded=True)
