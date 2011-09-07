import urllib2
import traceback
import logging
from time import sleep
from StringIO import StringIO
from ssl import SSLError

try:
  import ujson as json
except ImportError:
  import json

import db
import twitter
from worker import Job
from config import OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET

# TODO: we must handle blocked ids ourselves.
def stream(queue, user):
  api = twitter.Api(consumer_key=OAUTH_CONSUMER_KEY,
                    consumer_secret=OAUTH_CONSUMER_SECRET,
                    access_token_key=user['access_key'],
                    access_token_secret=user['access_secret'])
  user_timeline = user['timeline']
  user_jid = user['jid']
  user_screen_name = user['screen_name']
  user_at_screen_name = '@%s' % user_screen_name
  stream_logger = logging.getLogger('stream')
  wait_times = (0, 30, 60, 120, 240)
  wait_time_now_index = 0
  while True:
    try:
      user_stream_handler = api.user_stream()
      if wait_time_now_index:
        wait_time_now_index = 0

      # we must eliminate useless friends list first.
      length = user_stream_handler.readline().strip(' \r\n')
      length = int(length)
      user_stream_handler.read(length)

      while True:
        length = user_stream_handler.readline().strip(' \r\n')
        if length:
          length = int(length)
          data = json.loads(user_stream_handler.read(length))
          if 'event' not in data:
            if 'direct_message' in data:
              if user_timeline & db.MODE_DM:
                data = twitter.DirectMessage(data['direct_message'])
              else:
                data = None
            else:
              if user_timeline & db.MODE_HOME or (user_timeline & db.MODE_MENTION and user_at_screen_name in data['text']) \
              or data['user']['screen_name'] == user_screen_name:
                data = twitter.Status(data)
              else:
                data = None
            if data:
              queue.put(Job(user_jid, data=data, allow_duplicate=False, always=False))
          else:
            title = None
            if user_timeline & db.MODE_EVENT:
              if data['event'] == 'follow':
                title = '@%s is now following @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
              elif data['event'] == 'block':
                title = '@%s has blocked @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
              elif data['event'] == 'unblock':
                title = '@%s has unblocked @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
            if title:
              queue.put(Job(user_jid, title=title, always=False))
    except (urllib2.URLError, urllib2.HTTPError, SSLError), e:
      if isinstance(e, urllib2.HTTPError):
        if e.code == 401:
          stream_logger.error('User %s OAuth unauthorized, exiting.' % user_jid)
          return
        if e.code == 420:
          stream_logger.warn('User %s Streaming connect too often!' % user_jid)
          if not wait_time_now_index:
            wait_time_now_index = 1
      wait_time_now = wait_times[wait_time_now_index]
      if wait_time_now:
        stream_logger.info('%s: Sleep %d seconds.' % (user_jid, wait_time_now))
        sleep(wait_time_now)
      if wait_time_now_index < len(wait_times):
        wait_time_now_index += 1
    except BaseException:
      err = StringIO()
      traceback.print_exc(file=err)
      stream_logger.error(err.getvalue())



