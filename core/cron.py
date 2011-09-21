import time
import logging
import operator
from itertools import imap
from Queue import Queue

import db
from config import OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET
from worker import Job
from lib import twitter
from lib.util import StoppableThread
from lib.decorators import debug, threadstop

MAX_IDLE_TIME = 300
CRON_INTERVAL = 60
CRON_BLOCKED_IDS_INTERVAL = 3600
CRON_LIST_IDS_INTERVAL = 3600
CRON_VERIFY_CREDENTIAL_INTERVAL = 3600

logger = logging.getLogger('cron')

class CronStart(StoppableThread):
  _pool_size = db.get_users_count() // 20 + 1

  def __init__(self, queues):
    super(CronStart, self).__init__()
    self.queues = queues

  @threadstop
  def run(self):
    while True:
      last = time.time()
      self.running()
      now = time.time()
      if now - last >= CRON_INTERVAL and self._pool_size <= db.get_users_count():
        self._pool_size += 1
      else:
        remain = CRON_INTERVAL - (now - last)
        logger.debug('Sleep %.2f seconds.' % remain)
        self.sleep(remain)
      self.check_stop()


  def running(self):
    cron_queue = Queue()
    for user in db.get_all_users():
      if user['access_key'] and user['access_secret']:
        # event only exists in user streaming api.
        tl = user['timeline'] & ~db.MODE_EVENT
        if tl:
          if time.time() - user['last_update'] > MAX_IDLE_TIME:
            # if it's a long time since last update, we should abandon these old data.
            logger.debug('%s: Exceed %s seconds, all results won\'t be shown.' % (user['jid'], MAX_IDLE_TIME))
            queue = Queue()
          else:
            queue = self.queues[user['jid']]
          cron_queue.put((queue, user))
    for _ in xrange(self._pool_size):
      t = CronGetTimeline(cron_queue)
      t.start()
    cron_queue.join()


class CronGetTimeline(StoppableThread):
  def __init__(self, queue):
    super(CronGetTimeline, self).__init__()
    self.queue = queue

  def run(self):
    @debug()
    def fetch_home():
      data = api.get_home_timeline(since_id=user['last_home_id'])
      if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
        db.update_user(jid=user_jid, last_home_id=data[0]['id_str'])
        if not user_timeline & db.MODE_HOME:
          if user_timeline & db.MODE_MENTION:
            data = [x for x in data if '@%s' % user['screen_name'] in x['text']]
          else:
            data = list()
        return data

    @debug()
    def fetch_mention():
      if user_timeline & db.MODE_MENTION:
        data = api.get_mentions(since_id=user['last_mention_id'])
        if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
          db.update_user(jid=user_jid, last_mention_id=data[0]['id_str'])
          return data

    @debug()
    def fetch_dm():
      if user_timeline & db.MODE_DM:
        data = api.get_direct_messages(since_id=user['last_dm_id'])
        if data and isinstance(data, list) and isinstance(data[0], twitter.DirectMessage):
          db.update_user(jid=user_jid, last_dm_id=data[0]['id_str'])
          return data

    @debug()
    def fetch_list():
      if user_timeline & db.MODE_LIST:
        if user['list_user'] and user['list_name']:
          try:
            data = api.get_list_statuses(screen_name=user['list_user'], slug=user['list_name'],
              since_id=user['last_list_id'])
          except twitter.TwitterNotFoundError:
            user['timeline'] &= ~db.MODE_LIST
            db.update_user(id=user['id'], timeline=user['timeline'])
            queue.put(Job(user['jid'],
              title='List %s/%s not exists, disable List update.' % (user['list_user'], user['list_name'])))
          else:
            if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
              db.update_user(jid=user_jid, last_list_id=data[0]['id_str'])
              return data

    @debug()
    def fetch_search():
      if user_timeline == db.MODE_TRACK and user['track_words']:
        q = ' '.join(user['track_words'].split(','))
        data = api.get_search(q, since_id=user['last_search_id'])
        if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
          db.update_user(jid=user_jid, last_search_id=data[0]['id_str'])
          return data


    while not self.queue.empty():
      queue, user = self.queue.get()
      user_jid = user['jid']
      user_timeline = user['timeline']
      db.update_user(id=user['id'], last_update=int(time.time()))

      api = twitter.Api(consumer_key=OAUTH_CONSUMER_KEY,
        consumer_secret=OAUTH_CONSUMER_SECRET,
        access_token_key=user['access_key'],
        access_token_secret=user['access_secret'])
      all_data = list()

      data = fetch_dm()
      if data:
        queue.put(Job(user_jid, data=data, title='Direct Message:', allow_duplicate=False, always=False))
      data = fetch_list()
      if data:
        all_data.extend(data)
      data = fetch_mention()
      if data:
        all_data.extend(data)
      data = fetch_home()
      if data:
        all_data.extend(data)
      data = fetch_search()
      if data:
        all_data.extend(data)

      if all_data:
        all_data.sort(key=operator.itemgetter('id'))
        last = all_data[-1]['id']
        for i in range(len(all_data) - 2, -1, -1):
          if last == all_data[i]['id']:
            del all_data[i]
          else:
            last = all_data[i]['id']

      user_at_screen_name = '@%s' % user['screen_name']
      for data in all_data:
        if user_at_screen_name in data['text']:
          retweeted_status = data.get('retweeted_status')
          if retweeted_status and retweeted_status.get('in_reply_to_status_id_str'):
            data['retweeted_status']['in_reply_to_status'] = None
          elif data.get('in_reply_to_status_id_str'):
            data['in_reply_to_status'] = None

      if all_data:
        queue.put(Job(user_jid, data=all_data, allow_duplicate=False, always=False, reverse=False))

      self.queue.task_done()


class CronMisc(StoppableThread):
  # this cron check credentials, list ids, blocked_ids
  def __init__(self, xmpp):
    super(CronMisc, self).__init__()
    self._xmpp = xmpp

  @threadstop
  def run(self):
    while True:
      last = time.time()
      self.running()
      now = time.time()
      if now - last < CRON_INTERVAL:
        remain = CRON_INTERVAL - (now - last)
        logger.debug('Sleep %.2f seconds.' % remain)
        self.sleep(remain)
      self.check_stop()

  def running(self):
    for user in db.get_all_users():
      if user['access_key'] and user['access_secret']:
        self._api = twitter.Api(consumer_key=OAUTH_CONSUMER_KEY, consumer_secret=OAUTH_CONSUMER_SECRET,
          access_token_key=user['access_key'], access_token_secret=user['access_secret'])
        self._now = time.time()
        self._thread = self._xmpp.stream_threads.get(user['jid'])
        if self.verify_credential(user):
          self.refresh_blocked_ids(user)
          self.refresh_list_ids(user)

  @debug()
  def verify_credential(self, user):
    if self._now - user['last_verified'] > CRON_VERIFY_CREDENTIAL_INTERVAL:
      logger.debug('%s: check credential.' % user['jid'])
      try:
        twitter_user = self._api.verify_credentials()
      except twitter.TwitterUnauthorizedError:
        logger.debug('%s: credential is invalid.' % user['jid'])
        db.update_user(access_key=None, access_secret=None)
        if self._thread:
          self._thread.stop()
          return False
      else:
        if user['screen_name'] != twitter_user['screen_name']:
          logger.debug('%s: screen_name has been changed from %s to %s.' %
                       (user['jid'], user['screen_name'], twitter_user['screen_name']))
          db.update_user(id=user['id'], screen_name=twitter_user['screen_name'])
        return True
      finally:
        db.update_user(id=user['id'], last_verified=int(self._now))
    else:
      return True

  @debug()
  def refresh_blocked_ids(self, user):
    if self._now - user['blocked_ids_last_update'] > CRON_BLOCKED_IDS_INTERVAL:
      logger.debug('%s: refresh blocked ids.' % user['jid'])
      blocked_ids = self._api.get_blocking_ids(stringify_ids=True)
      if user['blocked_ids'] is None or set(blocked_ids) - set(user['blocked_ids'].split(',')):
        db.update_user(id=user['id'], blocked_ids=','.join(blocked_ids), blocked_ids_last_update=self._now)
        self._thread.user_changed()

  @debug()
  def refresh_list_ids(self, user):
    if user['list_user'] and user['list_name'] and self._now - user['list_ids_last_update'] > CRON_LIST_IDS_INTERVAL:
      logger.debug('%s: refresh list ids.' % user['jid'])
      cursor = -1
      list_ids = set()
      while cursor:
        result = self._api.get_list_members(user['list_user'], user['list_name'], cursor=cursor)
        list_ids.update(imap(operator.itemgetter('id_str'), result['users']))
        cursor = result['next_cursor']
      user = db.get_user_from_jid(user['jid'])
      if user['list_ids'] is None or list_ids - set(user['list_ids'].split(',')):
        db.update_user(id=user['id'], list_ids=list_ids, list_ids_last_update=self._now)
        self._thread.restart()
