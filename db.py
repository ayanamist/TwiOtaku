import os

import apsw

DB_PATH = os.path.dirname(__file__) + os.sep + 'twiotaku.db'

_conn_db = None
_cache = dict()

def init():
  global _conn_db
  if not _conn_db:
    _conn_db = apsw.Connection(DB_PATH)
    cursor = _conn_db.cursor()
    sql = dict(
      id_lists="""CREATE TABLE "id_lists" (
                "uid"  INTEGER NOT NULL,
                "short_id"  INTEGER NOT NULL,
                "long_id"  INTEGER NOT NULL,
                "type"  INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX "id_lists_uid_longid_type"
                ON "id_lists" ("uid", "long_id", "type");
                CREATE INDEX "is_lists_uid_shortid_type"
                ON "id_lists" ("uid", "short_id", "type");
                """,
      users="""CREATE TABLE "users" (
            "id"  INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            "enabled"  INTEGER NOT NULL DEFAULT 1,
            "jid"  TEXT NOT NULL,
            "screen_name"  TEXT,
            "access_key"  TEXT,
            "access_secret"  TEXT,
            "list_user"  TEXT,
            "list_id"  INTEGER,
            "list_name"  TEXT,
            "last_home_id"  INTEGER NOT NULL DEFAULT 0,
            "last_mention_id"  INTEGER NOT NULL DEFAULT 0,
            "last_dm_id"  INTEGER NOT NULL DEFAULT 0,
            "last_list_id"  INTEGER NOT NULL DEFAULT 0,
            "timeline"  INTEGER NOT NULL DEFAULT 3,
            "id_list_ptr"  INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX "users_enabled"
            ON "users" ("enabled");
            CREATE UNIQUE INDEX "users_id"
            ON "users" ("id");
            CREATE UNIQUE INDEX "users_jid"
            ON "users" ("jid");
            CREATE UNIQUE INDEX "users_enabled_timeline"
            ON "users" ("enabled", "timeline");
            """,
      statuses="""CREATE TABLE "statuses" (
              "id"  INTEGER NOT NULL,
              "json"  BLOB NOT NULL,
              "type"  INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY ("id") ON CONFLICT REPLACE
              );
              CREATE UNIQUE INDEX "status_id"
              ON "statuses" ("id", "type");
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
    for t in cursor.execute("SELECT name FROM sqlite_master WHERE type='table';"):
      t = t[0]
      if t in sql:
        del(sql[t])
    cursor.execute('BEGIN TRANSACTION')
    for v in sql.itervalues():
      cursor.execute(v)
    cursor.execute('COMMIT')
  return _conn_db

def get_user_from_jid(jid):
  cursor = _conn_db.cursor()
  user = dict()
  for u in cursor.execute('SELECT * FROM users WHERE jid=?', (jid, )):
    d = cursor.getdescription()
    for i in range(len(d)):
      user[d[i][0]] = u[i]
    break
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

def add_user(jid):
  cursor = _conn_db.cursor()
  sql = 'INSERT INTO users (jid) VALUES(?)'
  cursor.execute(sql, (jid,))

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