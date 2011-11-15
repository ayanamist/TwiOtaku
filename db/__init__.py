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

dbapi = __import__(DATABASE_TYPE.lower(), globals=globals(), locals=locals())

add_invite_code = dbapi.add_invite_code

add_status = dbapi.add_status

add_user = dbapi.add_user

delete_invite_code = dbapi.delete_invite_code

get_all_users = dbapi.get_all_users

get_invite_code = dbapi.get_invite_code

get_long_id_from_short_id = dbapi.get_long_id_from_short_id

get_short_id_from_long_id = dbapi.get_short_id_from_long_id

get_status = dbapi.get_status

get_user_from_jid = dbapi.get_user_from_jid

get_users_count = dbapi.get_users_count

purge_old_statuses = dbapi.purge_old_statuses

update_long_id_from_short_id = dbapi.update_long_id_from_short_id

update_user = dbapi.update_user

flush_status = dbapi.flush_status

