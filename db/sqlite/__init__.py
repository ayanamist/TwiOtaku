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

import functools
import logging
import os

try:
    from pysqlite2 import dbapi2 as sqlite3
except ImportError:
    import sqlite3

import config
from . import sqlthread
from . import sqlcommand


logger = logging.getLogger('sqlite')
sql_dir = os.path.join(os.path.dirname(__file__), 'sql')
database_dir = os.path.abspath(config.DATABASE_DIR)
if not os.path.exists(database_dir):
    os.makedirs(database_dir)
user_path = os.path.join(database_dir, 'twiotaku.db')
status_path = os.path.join(database_dir, 'status.db')

def write_decorator(f):
    @functools.wraps(f)
    def wrap(*args, **kwargs):
        command = sqlcommand.SQLCommand(f.__name__, *args, **kwargs)
        write_thread.process(command)
        return command.get_result()

    return wrap


def init_db_user(conn):
    tables = ['id_lists', 'invites', 'users']
    for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        if t[0] in tables:
            tables.remove(t[0])
    for v in tables:
        path = sql_dir + os.sep + v + '.sql'
        if os.path.exists(path):
            with open(path, 'r') as f:
                sql = f.read()
            conn.executescript(sql)
    conn.commit()


def init_db_status(conn):
    sql = True
    for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        if t[0] == 'statuses':
            sql = False
    if sql:
        path = sql_dir + os.sep + 'statuses.sql'
        if os.path.exists(path):
            with open(path, 'r') as f:
                sql = f.read()
            conn.executescript(sql)
    conn.commit()
    return conn


def init_conn_user():
    conn = sqlite3.connect(user_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_conn_status():
    conn = sqlite3.connect(status_path, check_same_thread=False)
    return conn


def init_write_thread(conn_user, conn_status):
    thread = sqlthread.SQLThread(conn_user=conn_user, conn_status=conn_status)
    return thread


def get_user_from_jid(jid):
    sql = 'SELECT * FROM users WHERE jid=?'
    cursor = conn_user.execute(sql, (jid, ))
    return cursor.fetchone()


@write_decorator
def update_user(id=None, jid=None, **kwargs):
    pass


def get_users_count():
    sql = 'SELECT COUNT(id) FROM users'
    cursor = conn_user.execute(sql)
    return cursor.fetchone()[0]


@write_decorator
def add_user(jid):
    pass


def get_all_users():
    sql = 'SELECT * FROM users'
    cursor = conn_user.execute(sql)
    return cursor.fetchall()


def iter_all_users():
    sql = 'SELECT * FROM users'
    cursor = conn_user.execute(sql)
    for x in cursor:
        yield x


def get_invite_code(invite_code):
    sql = 'SELECT id, create_time FROM invites WHERE id=?'
    cursor = conn_user.execute(sql, (invite_code, ))
    result = cursor.fetchone()
    return result[0], result[1] if result else None, None


@write_decorator
def add_invite_code(invite_code, create_time):
    pass


@write_decorator
def delete_invite_code(invite_code):
    pass


def get_short_id_from_long_id(uid, long_id, single_type):
    sql = 'SELECT short_id FROM id_lists WHERE uid=? AND long_id=? AND type=?'
    cursor = conn_user.execute(sql, (uid, long_id, single_type))
    result = cursor.fetchone()
    return result[0] if result else None


def get_long_id_from_short_id(uid, short_id):
    sql = 'SELECT long_id, type FROM id_lists WHERE uid=? AND short_id=?'
    cursor = conn_user.execute(sql, (uid, short_id))
    result = cursor.fetchone()
    return result[0] if result else None


@write_decorator
def update_long_id_from_short_id(uid, short_id, long_id, single_type):
    pass


def get_status(id_str):
    sql = 'SELECT data FROM statuses WHERE id_str=?'
    cursor = conn_status.execute(sql, (id_str,))
    result = cursor.fetchone()
    return result[0] if result else None


@write_decorator
def add_status(id_str, data_str, timestamp):
    pass


@write_decorator
def flush_status(force=False):
    pass


@write_decorator
def purge_old_statuses(from_timestamp):
    pass

conn_user = init_conn_user()
conn_status = init_conn_status()
init_db_user(conn_user)
init_db_status(conn_status)
write_thread = init_write_thread(conn_user=conn_user, conn_status=conn_status)