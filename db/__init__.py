from config import DATABASE_TYPE

MODE_NONE = 0
MODE_DM = 1
MODE_MENTION = 2
MODE_HOME = 4
MODE_LIST = 8
MODE_EVENT = 16
MODE_TRACK = 32

TYPE_STATUS = 0
TYPE_DM = 1

global add_invite_code
global add_status
global add_user
global delete_invite_code
global get_all_users
global get_invite_code
global get_long_id_from_short_id
global get_short_id_from_long_id
global get_status
global get_user_from_jid
global get_users_count
global purge_old_statuses
global update_long_id_from_short_id
global update_user

_db_type = DATABASE_TYPE.lower()
_vars = globals()
if _db_type == 'sqlite':
  import sqlite

  _vars['add_invite_code'] = sqlite.add_invite_code
  _vars['add_status'] = sqlite.add_status
  _vars['add_user'] = sqlite.add_user
  _vars['delete_invite_code'] = sqlite.delete_invite_code
  _vars['get_all_users'] = sqlite.get_all_users
  _vars['get_invite_code'] = sqlite.get_invite_code
  _vars['get_long_id_from_short_id'] = sqlite.get_long_id_from_short_id
  _vars['get_short_id_from_long_id'] = sqlite.get_short_id_from_long_id
  _vars['get_status'] = sqlite.get_status
  _vars['get_user_from_jid'] = sqlite.get_user_from_jid
  _vars['get_users_count'] = sqlite.get_users_count
  _vars['purge_old_statuses'] = sqlite.purge_old_statuses
  _vars['update_long_id_from_short_id'] = sqlite.update_long_id_from_short_id
  _vars['update_user'] = sqlite.update_user
else:
  raise NotImplementedError
