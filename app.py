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
def status(maxnum=10):
    db = DataBase(app.config['DB_PATH'])
    total_num = db.session.query(Danmu).count()
    danmus = db.session.query(Danmu)\
                       .order_by(Danmu.time.desc())\
                       .limit(10).all()
    for danmu in danmus:
        danmu.time -= datetime.timedelta(hours=8)
    return flask.render_template(
        'status.html',
        danmus=danmus, total_num=total_num)


if __name__ == "__main__":
    app.run('127.0.0.1', 8888,
            debug=True, threaded=True)
