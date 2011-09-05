import traceback
import logging
from StringIO import StringIO
from threading import Thread

import db
import twitter
from worker import Job
from config import OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET

def cron_start(xmpp):
  threads = list()
  for user in db.get_all_users():
    if user['access_key'] and user['access_secret']:
      t = Thread(target=cron_job, args=(xmpp, user))
      t.setDaemon(True)
      t.start()
      threads.append(t)
  for t in threads:
    t.join()


def cron_job(xmpp, user):
  jid = user['jid']
  if not user:
    return

  api = twitter.Api(consumer_key=OAUTH_CONSUMER_KEY,
                    consumer_secret=OAUTH_CONSUMER_SECRET,
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

  queue = xmpp.worker_queues[jid]
  logger = logging.getLogger('cron')

  try:
    if user['timeline'] & db.MODE_DM:
      data = api.get_direct_messages(since_id=user['last_dm_id'])
      if data and isinstance(data, list) and isinstance(data[0], twitter.DirectMessage):
        user['last_dm_id'] = data[0]['id_str']
        db.update_user(jid=jid, last_dm_id=user['last_dm_id'])
        queue.put(Job(data, jid, allow_duplicate=False))
  except BaseException:
    err = StringIO()
    traceback.print_exc(file=err)
    logger.error(err.getvalue())

  try:
    if user['timeline'] & db.MODE_MENTION:
      data = api.get_mentions(since_id=user['last_mention_id'])
      if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
        user['last_mention_id'] = data[0]['id_str']
        db.update_user(jid=jid, last_mention_id=user['last_mention_id'])
        queue.put(Job(data, jid, allow_duplicate=False))
  except BaseException:
    err = StringIO()
    traceback.print_exc(file=err)
    logger.error(err.getvalue())

  try:
    if user['timeline'] & db.MODE_LIST:
      if user['list_user'] and user['list_id']:
        try:
          data = api.get_list_statuses(user=user['list_user'], id=user['list_id'], since_id=user['last_list_id'])
        except twitter.TwitterNotFoundError:
          user['timeline'] &= ~db.MODE_LIST
          db.update_user(id=user['id'], timeline=user['timeline'])
          xmpp.send_message(user['jid'], 'List %s/%s not exists, disable List update.' % (user['list_user'], user['list_name']))
        else:
          if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
            user['last_list_id'] = data[0]['id_str']
            db.update_user(jid=jid, last_list_id=user['last_list_id'])
            queue.put(Job(data, jid, allow_duplicate=False))
  except BaseException:
    err = StringIO()
    traceback.print_exc(file=err)
    logger.error(err.getvalue())

  try:
    if user['timeline'] & db.MODE_HOME:
      data = api.get_home_timeline(since_id=user['last_home_id'])
      if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
        user['last_home_id'] = data[0]['id_str']
        db.update_user(jid=jid, last_home_id=user['last_home_id'])
        queue.put(Job(data, jid, allow_duplicate=False))
  except BaseException:
    err = StringIO()
    traceback.print_exc(file=err)
    logger.error(err.getvalue())


