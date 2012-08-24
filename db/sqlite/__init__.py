# Copyright 2011 ayanamist
# the program is distributed under the terms of the GNU General Public License
# This file is part of TwiOtaku.
#
#    Foobar is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    TwiOtaku is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with TwiOtaku.  If not, see <http://www.gnu.org/licenses/>.

import bz2
import functools
import logging
import os

try:
    from pysqlite2 import dbapi2 as sqlite3
except ImportError:
    import sqlite3

import config
from lib import mythread
from lib import myjson


_logger = logging.getLogger('sqlite')
_rwlock = mythread.ReadWriteLock()
_sql_dir = os.path.join(os.path.dirname(__file__), 'sql')
_database_dir = os.path.abspath(config.DATABASE_DIR)
if not os.path.exists(_database_dir):
    os.makedirs(_database_dir)
_user_path = os.path.join(_database_dir, 'twiotaku.db')

def write_decorator(f):
    @functools.wraps(f)
    def wrap(*args, **kwargs):
        with _rwlock.writelock:
            result = f(*args, **kwargs)
        return result

    return wrap


def read_decorator(f):
    @functools.wraps(f)
    def wrap(*args, **kwargs):
        with _rwlock.readlock:
            result = f(*args, **kwargs)
        return result

    return wrap


def _init_db_user(conn):
    tables = [x[:-4] for x in os.listdir(_sql_dir) if x[-4:].lower() == ".sql"]
    for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        if t[0] in tables:
            tables.remove(t[0])
    for v in tables:
        path = os.path.join(_sql_dir, v + '.sql')
        if os.path.exists(path):
            with open(path, 'r') as f:
                sql = f.read()
            conn.executescript(sql)
    conn.commit()


def _init_conn_user():
    conn = sqlite3.connect(_user_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@read_decorator
def get_user_from_jid(jid):
    sql = 'SELECT * FROM users WHERE jid=?'
    cursor = _conn_user.execute(sql, (jid, ))
    result = cursor.fetchone()
    return dict(result) if result else None


@write_decorator
def update_user(id=None, jid=None, **kwargs):
    if id is None and jid is None:
        raise TypeError('The method takes at least one argument.')
    if kwargs:
        cols = list()
        values = list()
        for k, v in kwargs.iteritems():
            cols.append('%s=?' % k)
            values.append(v)
        if id:
            cond = 'id=?'
            values.append(id)
        else:
            cond = 'jid=?'
            values.append(jid)
        sql = 'UPDATE users SET %s WHERE %s' % (','.join(cols), cond)
        _conn_user.execute(sql, values)
        _conn_user.commit()


@read_decorator
def get_users_count():
    sql = 'SELECT COUNT(id) FROM users'
    cursor = _conn_user.execute(sql)
    return cursor.fetchone()[0]


@write_decorator
def add_user(jid):
    sql = 'INSERT INTO users (jid) VALUES(?)'
    _conn_user.execute(sql, (jid,))
    _conn_user.commit()


@read_decorator
def get_all_users():
    return list(iter_all_users())


@read_decorator
def iter_all_users():
    sql = 'SELECT * FROM users'
    cursor = _conn_user.execute(sql)
    for x in cursor:
        yield dict(x)


@read_decorator
def verify_invite_code(invite_code):
    sql = 'SELECT create_time FROM invites WHERE id=?'
    cursor = _conn_user.execute(sql, (invite_code, ))
    result = cursor.fetchone()
    return result[0] if result else None


@write_decorator
def add_invite_code(invite_code, create_time):
    sql = 'INSERT INTO invites (id, create_time) VALUES(?,?)'
    _conn_user.execute(sql, (invite_code, create_time))


@write_decorator
def delete_invite_code(invite_code):
    sql = 'DELETE FROM invites WHERE id=?'
    _conn_user.execute(sql, (invite_code,))


@read_decorator
def get_short_id_from_long_id(uid, long_id, single_type):
    sql = 'SELECT short_id FROM id_lists WHERE uid=? AND long_id=? AND type=?'
    cursor = _conn_user.execute(sql, (uid, long_id, single_type))
    result = cursor.fetchone()
    return result[0] if result else None


@read_decorator
def get_long_id_from_short_id(uid, short_id):
    sql = 'SELECT long_id, type FROM id_lists WHERE uid=? AND short_id=?'
    cursor = _conn_user.execute(sql, (uid, short_id))
    result = cursor.fetchone()
    return tuple(result) if result else (None, None)


@write_decorator
def update_long_id_from_short_id(uid, short_id, long_id, single_type):
    sql = 'DELETE FROM id_lists WHERE uid=? AND short_id=?'
    _conn_user.execute(sql, (uid, short_id))
    sql = 'INSERT INTO id_lists (uid, short_id, long_id, type) VALUES(?, ?, ?, ?)'
    _conn_user.execute(sql, (uid, short_id, long_id, single_type))
    _conn_user.commit()


@read_decorator
def get_long_id_count(long_id):
    sql = 'SELECT COUNT(long_id) FROM id_lists WHERE long_id=?'
    cursor = _conn_user.execute(sql, (long_id,))
    return cursor.fetchone()[0]


@write_decorator
def set_cache(long_id, value):
    sql = "REPLACE INTO statuses (id, value) VALUES(?, ?)"
    _conn_user.execute(sql, (long_id, buffer(bz2.compress(myjson.dumps(value)))))
    _conn_user.commit()


@read_decorator
def get_cache(long_id):
    sql = "SELECT value FROM statuses WHERE id=?"
    cursor = _conn_user.execute(sql, (long_id,))
    result = cursor.fetchone()
    if result:
        return myjson.loads(bz2.decompress(str(result[0])))


@write_decorator
def delete_cache(long_id):
    sql = "DELETE FROM statuses WHERE id=?"
    _conn_user.execute(sql, (long_id,))


def close():
    _conn_user.commit()
    _conn_user.close()

_conn_user = _init_conn_user()
_init_db_user(_conn_user)
