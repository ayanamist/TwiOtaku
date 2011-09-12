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
_vars = globals()
if _db_type == 'sqlite':
  import sqlite

  _vars['add_invite_code'] = sqlite.add_invite_code
  _vars['add_status'] = sqlite.add_status
  _vars['add_user'] = sqlite.add_user
  _vars['begin_transaction'] = sqlite.begin_transaction
  _vars['commit_transaction'] = sqlite.commit_transaction
  _vars['delete_invite_code'] = sqlite.delete_invite_code
  _vars['delete_status'] = sqlite.delete_status
  _vars['get_all_users'] = sqlite.get_all_users
  _vars['get_invite_code'] = sqlite.get_invite_code
  _vars['get_long_id_from_short_id'] = sqlite.get_long_id_from_short_id
  _vars['get_short_id_from_long_id'] = sqlite.get_short_id_from_long_id
  _vars['get_status'] = sqlite.get_status
  _vars['get_user_from_jid'] = sqlite.get_user_from_jid
  _vars['get_users_count'] = sqlite.get_users_count
  _vars['init'] = sqlite.init
  _vars['update_long_id_from_short_id'] = sqlite.update_long_id_from_short_id
  _vars['update_user'] = sqlite.update_user
elif _db_type == 'leveldb':
  raise NotImplementedError
else:
  raise NotImplementedError
