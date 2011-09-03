import traceback
import logging
from StringIO import StringIO
from threading import Thread

import db
import twitter

def cron_start(xmpp):
  threads = list()
  for jid in xmpp.online_users:
    t = Thread(target=cron_job, args=(xmpp, jid))
    t.setDaemon(True)
    t.start()
    threads.append(t)
  for t in threads:
    t.join()

def cron_job(xmpp, jid):
  user = db.get_user_from_jid(jid)
  if not user:
    return

  api = twitter.Api(consumer_key=xmpp._config['OAUTH_CONSUMER_KEY'],
                    consumer_secret=xmpp._config['OAUTH_CONSUMER_SECRET'],
                    access_token_key=user['access_key'],
                    access_token_secret=user['access_secret'])
  try:
    screen_name = api.verify_credentials()['screen_name']
  except twitter.TwitterAuthenticationError:
    db.update_user(jid=jid, access_key=None, access_secret=None)
    del xmpp.online_clients[jid]
    return
  if screen_name != user['screen_name']:
    user['screen_name'] = screen_name
    db.update_user(jid=jid, screen_name=screen_name)

  queue = xmpp.tbd_queues.get(jid)
  if queue is None:
    return

  cursor = db.begin_transaction()
  try:
    if user['timeline'] & db.MODE_DM:
      data = api.get_direct_messages(since_id=user['last_dm_id'])
      if data and isinstance(data, list) and isinstance(data[0], twitter.DirectMessage):
        user['last_dm_id'] = data[0]['id']
        db.update_user(jid=jid, cursor=cursor, last_dm_id=user['last_dm_id'])
        queue.put((data, jid, None))
    if user['timeline'] & db.MODE_MENTION:
      data = api.get_mentions(since_id=user['last_mention_id'])
      if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
        user['last_mention_id'] = data[0]['id']
        db.update_user(jid=jid, cursor=cursor, last_mention_id=user['last_mention_id'])
        queue.put((data, jid, None))
    if user['timeline'] & db.MODE_LIST:
      data = api.get_list_statuses(user=user['list_user'], id=user['list_id'], since_id=user['last_list_id'])
      if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
        user['last_list_id'] = data[0]['id']
        db.update_user(jid=jid, cursor=cursor, last_list_id=user['last_list_id'])
        queue.put((data, jid, None))
    if user['timeline'] & db.MODE_HOME:
      data = api.get_home_timeline(since_id=user['last_home_id'])
      if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
        user['last_home_id'] = data[0]['id']
        db.update_user(jid=jid, cursor=cursor, last_home_id=user['last_home_id'])
        queue.put((data, jid, None))

  except BaseException:
    err = StringIO()
    traceback.print_exc(file=err)
    xmpp_logger = logging.getLogger('cron')
    xmpp_logger.error(err.getvalue())
  finally:
    db.end_transaction(cursor)


