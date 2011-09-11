from config import DATABASE_TYPE

MODE_NONE = 0
MODE_DM = 1
MODE_MENTION = 2
MODE_HOME = 4
MODE_LIST = 8
MODE_EVENT = 16

TYPE_STATUS = 0
TYPE_DM = 1

_db_type = DATABASE_TYPE.lower()
if _db_type == 'sqlite':
elif _db_type == 'leveldb':
  raise NotImplementedError
else:
  raise NotImplementedError
