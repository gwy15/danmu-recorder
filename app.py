import datetime

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
    total_num = db.session.query(Danmu).count()

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
    for danmu in danmus:
        danmu.time -= datetime.timedelta(hours=8)
    return flask.render_template(
        'status.html',
        danmus=danmus, total_num=total_num)


if __name__ == "__main__":
    app.run('127.0.0.1', 8888,
            debug=True, threaded=True)
