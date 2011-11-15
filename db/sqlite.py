import os
import logging
from time import mktime
from email.utils import parsedate

try:
  import ujson as json
except ImportError:
  import json

import apsw

try:
  import ujson as json
except ImportError:
  import json

from config import DATABASE_DIR

RETRY_TIMEOUT = 3000 # add a retry timeout for busy handling
database_dir = os.path.abspath(DATABASE_DIR)
_db_path = os.path.abspath(database_dir + os.sep + 'twiotaku.db')
_status_path = os.path.abspath(database_dir + os.sep + 'status.db')
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
sql = dict(
  id_lists="""CREATE TABLE "id_lists" (
            "uid"  INTEGER NOT NULL,
            "short_id"  INTEGER NOT NULL,
            "long_id"  TEXT NOT NULL,
            "type"  INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX "id_lists_uid_longid_type"
            ON "id_lists" ("uid", "long_id", "type");
            CREATE INDEX "is_lists_uid_shortid_type"
            ON "id_lists" ("uid", "short_id");
            """,
  users="""CREATE TABLE "users" (
        "id"  INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        "jid"  TEXT NOT NULL,
        "screen_name"  TEXT,
        "access_key"  TEXT,
        "access_secret"  TEXT,
        "last_verified"  INTEGER NOT NULL DEFAULT 0,
        "list_user"  TEXT,
        "list_name"  TEXT,
        "last_home_id"  TEXT,
        "last_mention_id"  TEXT,
        "last_dm_id"  TEXT,
        "last_list_id"  TEXT,
        "last_search_id"  TEXT,
        "last_update"  INTEGER NOT NULL DEFAULT 0,
        "timeline"  INTEGER NOT NULL DEFAULT 3,
        "id_list_ptr"  INTEGER NOT NULL DEFAULT 0,
        "msg_tpl"  BLOB,
        "date_fmt"  TEXT,
        "always"  INTEGER NOT NULL DEFAULT 0,
        "track_words"  TEXT,
        "list_ids"  TEXT,
        "list_ids_last_update"  INTEGER NOT NULL DEFAULT 0,
        "blocked_ids" TEXT,
        "blocked_ids_last_update" INTEGER NOT NULL DEFAULT 0
        );
        CREATE UNIQUE INDEX "users_id"
        ON "users" ("id");
        CREATE UNIQUE INDEX "users_jid"
        ON "users" ("jid");
        """,
  invites="""CREATE TABLE "invites" (
        "id"  TEXT NOT NULL,
        "create_time"   INTEGER NOT NULL,
        PRIMARY KEY ("id") ON CONFLICT FAIL
        );
        CREATE UNIQUE INDEX "invite_id"
        ON "invites" ("id");
        """,
)
for t in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'"):
  t = t[0]
  if t in sql:
    del(sql[t])
for v in sql.itervalues():
  cursor.execute(v)
_conn_status = apsw.Connection(_status_path)
_conn_status.setbusytimeout(RETRY_TIMEOUT)
cursor = _conn_status.cursor()
sql = """CREATE TABLE "statuses" (
            "id_str"  TEXT NOT NULL,
            "timestamp"  INTEGER NOT NULL,
            "data"  BLOB NOT NULL,
            PRIMARY KEY ("id_str") ON CONFLICT REPLACE
            );
            CREATE UNIQUE INDEX "status_id"
            ON "statuses" ("id_str");
            CREATE INDEX "timestamp"
            ON "statuses" ("timestamp");
            """
for t in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'"):
  t = t[0]
  if t == 'statuses':
    sql = None
if sql:
  cursor.execute(sql)
