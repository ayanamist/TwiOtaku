import os
import logging
from time import mktime
from email.utils import parsedate

import apsw

import lib.myjson as json
from config import DATABASE_DIR

RETRY_TIMEOUT = 3000 # add a retry timeout for busy handling
database_dir = os.path.abspath(DATABASE_DIR)
_db_path = os.path.join(database_dir, 'twiotaku.db')
_status_path = os.path.join(database_dir, 'status.db')
_sql_dir = os.path.join(os.path.dirname(__file__), 'sql')
_conn_db = None
_conn_status = None
_status_queue = list()
logger = logging.getLogger('sqlite')

def get_user_from_jid(jid):
  cursor = _conn_db.cursor()
  user = dict()
  for u in cursor.execute('SELECT * FROM users WHERE jid=?', (jid, )):
    d = cursor.getdescription()
    for i in range(len(d)):
      user[d[i][0]] = u[i]
  return user


def update_user(id=None, jid=None, **kwargs):
  if id is None and jid is None:
    raise TypeError('The method takes at least one argument.')
  if kwargs:
    cursor = _conn_db.cursor()
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
    cursor.execute(sql, values)


def get_users_count():
  cursor = _conn_db.cursor()
  sql = 'SELECT COUNT(id) FROM users'
  cursor.execute(sql)
  return list(cursor)[0][0]


def add_user(jid):
  cursor = _conn_db.cursor()
  sql = 'INSERT INTO users (jid) VALUES(?)'
  cursor.execute(sql, (jid,))


def get_all_users():
  cursor = _conn_db.cursor()
  sql = 'SELECT * FROM users'
  d = None
  for u in cursor.execute(sql):
    if d is None:
      d = cursor.getdescription()
    user = dict()
    for i in range(len(d)):
      user[d[i][0]] = u[i]
    yield user


def get_invite_code(invide_code):
  cursor = _conn_db.cursor()
  for u in cursor.execute('SELECT id, create_time FROM invites WHERE id=?', (invide_code, )):
    return u
  return None, None


def add_invite_code(invite_code, create_time):
  cursor = _conn_db.cursor()
  sql = 'INSERT INTO invites (id, create_time) VALUES(?,?)'
  cursor.execute(sql, (invite_code, create_time))


def delete_invite_code(invite_code):
  cursor = _conn_db.cursor()
  sql = 'DELETE FROM invites WHERE id=?'
  cursor.execute(sql, (invite_code,))


def get_short_id_from_long_id(uid, long_id, single_type):
  cursor = _conn_db.cursor()
  sql = 'SELECT short_id FROM id_lists WHERE uid=? AND long_id=? AND type=?'
  for x in cursor.execute(sql, (uid, long_id, single_type)):
    return x[0]


def get_long_id_from_short_id(uid, short_id):
  cursor = _conn_db.cursor()
  sql = 'SELECT long_id, type FROM id_lists WHERE uid=? AND short_id=?'
  for x in cursor.execute(sql, (uid, short_id)):
    return x[0], x[1]
  return None, None


def update_long_id_from_short_id(uid, short_id, long_id, single_type):
  cursor = _conn_db.cursor()
  sql = 'DELETE FROM id_lists WHERE uid=? AND short_id=?'
  cursor.execute(sql, (uid, short_id))
  sql = 'INSERT INTO id_lists (uid, short_id, long_id, type) VALUES(?, ?, ?, ?)'
  cursor.execute(sql, (uid, short_id, long_id, single_type))


def get_status(id_str):
  flush_status(force=True)
  cursor = _conn_status.cursor()
  sql = 'SELECT data FROM statuses WHERE id_str=?'
  for data, in cursor.execute(sql, (id_str,)):
    return data


def add_status(data):
  global _status_queue
  id_str = data.get('id_str')
  timestamp = parsedate(data.get('created_at'))
  if id_str and timestamp:
    timestamp = int(mktime(timestamp))
    _status_queue.append((id_str, timestamp, json.dumps(data)))
    flush_status()


def flush_status(force=False):
  global _status_queue
  if len(_status_queue) > 500 or force:
    cursor = _conn_status.cursor()
    try:
      cursor.execute('BEGIN')
    except apsw.SQLError, e:
      logger.warning(e)
    try:
      while _status_queue:
        id_str, timestamp, data = _status_queue.pop()
        cursor.execute('INSERT OR REPLACE INTO statuses (id_str, data, timestamp) VALUES(?,?,?)', (id_str, data, timestamp))
    finally:
      try:
        cursor.execute('COMMIT')
      except apsw.SQLError:
        pass

def purge_old_statuses(from_timestamp):
  cursor = _conn_status.cursor()
  cursor.execute('DELETE FROM statuses WHERE timestamp<?', (from_timestamp,))

if not os.path.exists(database_dir):
  os.makedirs(database_dir)

_conn_db = apsw.Connection(_db_path)
_conn_db.setbusytimeout(RETRY_TIMEOUT)
cursor = _conn_db.cursor()
tables = ['id_lists', 'invites', 'users']
for t in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'"):
  t = t[0]
  try:
    i = tables.index(t)
  except ValueError:
    i = -1
  if t >= 0:
    del(tables[t])
for v in tables:
  path = _sql_dir + os.sep + v + '.sql'
  if os.path.exists(path):
    f = open(path, 'r')
    sql = f.read()
    f.close()
    cursor.execute(v)
_conn_status = apsw.Connection(_status_path)
_conn_status.setbusytimeout(RETRY_TIMEOUT)
cursor = _conn_status.cursor()
sql = True
for t in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'"):
  t = t[0]
  if t == 'statuses':
    sql = False
if sql:
  path = _sql_dir + os.sep + 'statuses.sql'
  if os.path.exists(path):
    f = open(path, 'r')
    sql = f.read()
    f.close()
    cursor.execute(sql)
