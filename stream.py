import urllib2
import threading
import logging
from time import sleep, time
from ssl import SSLError

try:
  import ujson as json
except ImportError:
  import json

import db
import twitter
from worker import Job
from util import debug
from config import OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET

class ThreadStop(Exception):
  pass


class StreamThread(threading.Thread):
  """Thread class with a stop() method. The thread itself has to check
  regularly for the stopped() condition."""

  def __init__(self, xmpp, bare_jid):
    super(StreamThread, self).__init__()
    self._stop = threading.Event()
    self.xmpp = xmpp
    self.bare_jid = bare_jid
    self.blocked_ids = list()

  def stop(self):
    self._stop.set()

  def stopped(self):
    return self._stop.is_set()

  # TODO: auto add in_reply_to_status for all mentions
  # TODO: implement track and follow (list) (possibly via select?)

  def run(self):
    @debug('userstreaming')
    def running():
      def read_line(fp):
        s = ''
        while True:
          char = fp.read(1)
          s += char
          if char == '\n':
            return s

      def read_data(fp):
        while True:
          # we should not directly use readline method of user_stream_handler,
          # because it has buffer which will block unintentionally
          length = read_line(user_stream_handler).strip(' \r\n')
          if length:
            return json.loads(user_stream_handler.read(int(length)))

      def refresh_blocked_ids():
        @debug('refresh_blocked_ids')
        def wrap():
          return api.get_blocking_ids()

        result = wrap()
        if result is not None:
          self.blocked_ids = result

      def check_stop():
        if self.stopped():
          raise ThreadStop


      queue = self.xmpp.worker_queues[self.bare_jid]
      user = db.get_user_from_jid(self.bare_jid)
      api = twitter.Api(consumer_key=OAUTH_CONSUMER_KEY,
        consumer_secret=OAUTH_CONSUMER_SECRET,
        access_token_key=user['access_key'],
        access_token_secret=user['access_secret'])
      user_timeline = user['timeline']
      user_jid = user['jid']
      user_screen_name = user['screen_name']
      user_at_screen_name = '@%s' % user_screen_name
      wait_times = (0, 30, 60, 120, 240)
      wait_time_now_index = 0
      last_blocked_ids_update = time()
      refresh_blocked_ids_interval = 3600
      refresh_blocked_ids()
      stream_logger = logging.getLogger('user streaming')
      while True:
        try:
          check_stop()
          user_stream_handler = api.user_stream()
          if wait_time_now_index:
            wait_time_now_index = 0

          # read out friends ids and eliminate them because they are useless.
          read_data(user_stream_handler)

          while True:
            check_stop()
            time_now = time()
            if time_now - last_blocked_ids_update >= refresh_blocked_ids_interval:
              refresh_blocked_ids()
              last_blocked_ids_update = time_now
            data = read_data(user_stream_handler)
            if 'event' in data:
              title = None
              if user_timeline & db.MODE_EVENT:
                if data['event'] == 'follow':
                  title = '@%s is now following @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
                elif data['event'] == 'block':
                  refresh_blocked_ids()
                  title = '@%s has blocked @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
                elif data['event'] == 'unblock':
                  refresh_blocked_ids()
                  title = '@%s has unblocked @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
                elif data['event'] == 'list_member_added':
                  pass
                elif data['event'] == 'list_member_removed':
                  pass
              if title:
                queue.put(Job(user_jid, title=title, always=False))
            elif 'delete' in data:
              if 'status' in data['delete']:
                db.delete_status(data['delete']['status']['id_str'])
            else:
              if 'direct_message' in data:
                if user_timeline & db.MODE_DM:
                  data = twitter.DirectMessage(data['direct_message'])
                else:
                  data = None
              else:
                # It should not save status here, because sqlite only accepts around 60 transactions per second,
                # and for feature of user streaming, it's easy to overcome this limitation which makes the whole
                # program more and more slowly, also cron threads will collect the same items at the same time.
                if data['user']['id_str'] not in self.blocked_ids and user_timeline & db.MODE_HOME\
                   or (user_timeline & db.MODE_MENTION and user_at_screen_name in data['text'])\
                or data['user']['screen_name'] == user_screen_name:
                  data = twitter.Status(data)
                else:
                  data = None
              if data:
                queue.put(Job(user_jid, data=data, allow_duplicate=False, always=False))
        except (urllib2.URLError, urllib2.HTTPError, SSLError), e:
          if isinstance(e, urllib2.HTTPError):
            if e.code == 401:
              stream_logger.error('User %s OAuth unauthorized, exiting.' % user_jid)
              raise ThreadStop
            if e.code == 420:
              stream_logger.warn('User %s Streaming connect too often!' % user_jid)
              if not wait_time_now_index:
                wait_time_now_index = 1
          wait_time_now = wait_times[wait_time_now_index]
          if wait_time_now:
            stream_logger.info('%s: Sleep %d seconds.' % (user_jid, wait_time_now))
            for _ in xrange(wait_time_now):
              check_stop()
              sleep(1)
          if wait_time_now_index < len(wait_times):
            wait_time_now_index += 1

    try:
      running()
    except ThreadStop:
      del self.xmpp.stream_threads[self.bare_jid]
      return
