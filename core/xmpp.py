import random
import time
import operator
from itertools import ifilter
from Queue import Queue
from urlparse import parse_qsl
from email.utils import parsedate
from datetime import datetime

import db
from config import OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET, MAX_CONVERSATION_NUM, ADMIN_USERS
from worker import Job
from lib import oauth, twitter
from lib.util import Util
from lib.logger import debug

SHORT_COMMANDS = {
  '@': 'reply',
  'r': 'reply',
  'd': 'dm',
  'ra': 'replyall',
  'ho': 'home',
  'lt': 'list',
  'tl': 'timeline',
  'fo': 'follow',
  'unfo': 'unfollow',
  'b': 'block',
  'ub': 'unblock',
  'm': 'msg',
  'f': 'fav',
  'uf': 'unfav',
  'u': 'user',
  '?': 'help',
  'h': 'help',
  }

class XMPPMessageHandler(object):
  def __init__(self, xmpp):
    self._xmpp = xmpp

  @debug
  def process(self, msg):
    self._jid = str(msg['from'])
    self._bare_jid = self._xmpp.getjidbare(self._jid).lower()
    self._queue = self._xmpp.worker_queues.get(self._bare_jid, Queue())
    self._user = db.get_user_from_jid(self._bare_jid)
    if self._user:
      self._util = Util(self._user)
      self._api = twitter.Api(consumer_key=OAUTH_CONSUMER_KEY, consumer_secret=OAUTH_CONSUMER_SECRET,
        access_token_key=self._user.get('access_key'), access_token_secret=self._user.get('access_secret'))
    try:
      result = self.parse_command(msg['body'])
    except Exception, e:
      result = u'%s: %s' % (e.__class__.__name__, unicode(e))
    if result:
      msg.reply(result).send()

  def parse_command(self, cmd):
    if cmd[0] == '-' or cmd[0] == ' ':
      args = cmd[1:].lstrip().split(' ')
      if args[0] in SHORT_COMMANDS:
        args[0] = SHORT_COMMANDS[args[0]]
      if not self._user and args[0] != 'invite':
        return
      func_name = 'func_' + args[0]
      func = getattr(self, func_name)
      return func(*args[1:])
    else:
      status = self._api.post_update(cmd.encode('UTF8'))
      self._queue.put(Job(self._jid, data=status, allow_duplicate=False))

  def func_oauth(self):
    consumer = oauth.Consumer(OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET)
    client = oauth.Client(consumer)
    resp = client.request(twitter.REQUEST_TOKEN_URL)
    if resp:
      _request_token = dict(parse_qsl(resp))
      oauth_token = _request_token['oauth_token']
      redirect_url = "%s?oauth_token=%s" % (twitter.AUTHORIZATION_URL, oauth_token)
      db.update_user(self._user['id'], access_key=oauth_token, access_secret=None)
      return u'Please visit below url to get PIN code:\n%s\nthen you should use "-bind PIN" command to actually bind your Twitter.' % redirect_url
    else:
      return u'Network error.'

  def func_bind(self, pin_code):
    if self._user['access_key']:
      token = oauth.Token(self._user['access_key'])
      if type(pin_code) is unicode:
        pin_code = pin_code.encode('UTF8')
      token.set_verifier(pin_code)
      consumer = oauth.Consumer(OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET)
      client = oauth.Client(consumer, token)
      resp = client.request(twitter.ACCESS_TOKEN_URL, "POST")
      if not resp:
        return u'Network error.'
      access_token = dict(parse_qsl(resp))
      if 'oauth_token' in access_token:
        db.update_user(self._user['id'], access_key=access_token['oauth_token'], access_secret=access_token['oauth_token_secret'],
          screen_name=access_token['screen_name'])
        self._xmpp.add_online_user(self._bare_jid)
        return u'Associated you with @%s.' % access_token['screen_name']
    return u'Invalid PIN code.'

  def func_invite(self, invite_code=None):
    def generate_invite_code():
      valid_chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
      return ''.join(random.choice(valid_chars) for _ in xrange(8))

    expire_days = 3

    if invite_code:
      invite_code, create_time = db.get_invite_code(invite_code)
      if invite_code and create_time and create_time + expire_days * 24 * 3600 > time.time():
        db.delete_invite_code(invite_code)
        if not self._user:
          db.add_user(self._bare_jid)
        return u'Your account %s has been added, enjoy using TwiOtaku.' % self._bare_jid
      else:
        return u'Invite code is invalid or expired.'
    elif self._bare_jid in ADMIN_USERS:
      invite_code = generate_invite_code()
      create_time = int(time.time())
      db.add_invite_code(invite_code, create_time)
      return u'You have generated a new invite code which is available for %d days: %s' % (expire_days, invite_code)

  def func_user(self, short_id_or_screen_name=None):
    if short_id_or_screen_name and short_id_or_screen_name[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(short_id_or_screen_name)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        twitter_user = status['user']
      else:
        direct_message = self._api.get_direct_message(long_id)
        twitter_user = direct_message['sender']
    else:
      if short_id_or_screen_name is None:
        short_id_or_screen_name = self._user['screen_name']
      twitter_user = self._api.get_user(screen_name=short_id_or_screen_name)
    texts = [u'User @%s (%s):' % (twitter_user['screen_name'], twitter_user['name'])]
    if twitter_user['protected']:
      follow_str = [u'Protected user. ']
    else:
      follow_str = [u'']
    if twitter_user['following']:
      follow_str.append(u'You are following.')
    else:
      if twitter_user['follow_request_sent']:
        follow_str.append(u'You have sent follow request.')
      else:
        follow_str.append(u'You are not following.')
    texts.append(''.join(follow_str))
    avatar_url = twitter_user['profile_image_url_https']
    i = avatar_url.rfind('_normal.')
    if i != -1:
      avatar_url = avatar_url[:i] + avatar_url[i + 7:]
    texts.append(u'Avatar: %s' % avatar_url)
    if twitter_user['url']:
      texts.append(u'Web: %s' % twitter_user['url'])
    if twitter_user['location']:
      texts.append(u'Location: %s' % twitter_user['location'])
    texts.append(u'Following: %d' % twitter_user['friends_count'])
    texts.append(u'Followers: %d' % twitter_user['followers_count'])
    texts.append(u'Tweets: %d' % twitter_user['statuses_count'])
    join_time = time.mktime(parsedate(twitter_user['created_at']))
    join_time += 28800
    join_time = time.strftime(u'%Y-%m-%d %H:%M:%S', time.localtime(join_time))
    texts.append(u'Joined at: %s' % join_time)
    texts.append(u'Tweets per day: %.2f' % (twitter_user['statuses_count'] * 86400 /
                                            (time.time() - time.mktime(parsedate(twitter_user['created_at'])))))
    if twitter_user['description']:
      texts.append(u'Bio: %s' % twitter_user['description'])
    return '\n'.join(texts)

  def func_list(self, *args):
    length = len(args)
    if not length:
      lists = self._api.get_all_lists()
      texts = list()
      for l in lists:
        texts.append(u'%s %s: %s' %
                     (l['slug'] if l['user']['screen_name'] == self._user['screen_name'] else u'%s/%s' % (l['user']['screen_name'],
                                                                                                          l['slug']), l['mode'], l['description']))
      return u'Subscribing Lists:\n' + '\n'.join(texts)
    elif length == 1 or (length == 2 and args[1].isdigit()):
      try:
        page = int(args[1]) if length == 2 else 1
      except ValueError:
        return u'Unknown page number: %s.' % args[1]
      list_user_name = args[0]
      path = list_user_name.split('/', 1)
      if len(path) == 1:
        list_user = self._user['screen_name']
        list_name = path[0]
      else:
        list_user, list_name = path
      statuses = self._api.get_list_statuses(list_user, list_name, page=page)
      self._queue.put(Job(self._jid, data=statuses, title='List %s Statuses: Page %d' % (list_user_name, page)))
    else:
      list_command = args[0].lower()
      if list_command == 'info' and length == 2:
        list_user_name = args[1]
        path = list_user_name.split('/', 1)
        if len(path) == 1:
          list_user = self._user['screen_name']
          list_name = path[0]
        else:
          list_user, list_name = path
        l = self._api.get_list(screen_name=list_user, slug=list_name)
        texts = (u'List %s/%s %s: %s' %
                 (l['user']['screen_name'], l['slug'], l['mode'], u'You are following.' if l['following'] else u''),
                 u'Member Count: %d' % l['member_count'], u'Subscriber Count: %d' % l['subscriber_count'],
                 u'Description: %s' % l['description'])
        return '\n'.join(texts)
      elif list_command in ('add', 'del') and 2 <= length <= 3:
        if length == 2:
          if list_command == 'add':
            self._api.create_list(args[1], public=False)
            return u'Created private list %s.' % args[1]
          else:
            self._api.destroy_list(self._user['screen_name'], args[1])
            return u'Deleted list %s.' % args[1]
        else:
          if list_command == 'add':
            self._api.create_list_member(self._user['screen_name'], args[1], args[2])
            result = u'Added %s to list %s.' % (args[2], args[1])
          else:
            self._api.destroy_list_member(self._user['screen_name'], args[1], args[2])
            result = u'Removed %s from list %s.' % (args[2], args[1])
          if self._user['screen_name'] == self._user['list_user'] and args[1] == self._user['list_name']:
            db.update_user(id=self._user['id'], list_ids_last_update=0)
          return result
      else:
        raise TypeError('Not supported list command.')

  def func_home(self, page=1):
    try:
      page = int(page)
    except ValueError:
      return u'Unknown page number: %s.' % page
    statuses = self._api.get_home_timeline(page=page)
    self._queue.put(Job(self._jid, data=statuses, title='Home Timeline: Page %d' % page))

  def func_timeline(self, screen_name_or_short_id=None, page=1):
    try:
      page = int(page)
    except ValueError:
      return u'Unknown page number: %s.' % page
    if not screen_name_or_short_id:
      screen_name_or_short_id = self._user['screen_name']
    elif screen_name_or_short_id[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(screen_name_or_short_id)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        screen_name_or_short_id = status['user']['screen_name']
      else:
        direct_message = self._api.get_direct_message(long_id)
        screen_name_or_short_id = direct_message['sender_screen_name']
    statuses = self._api.get_user_timeline(screen_name=screen_name_or_short_id, page=page)
    self._queue.put(Job(self._jid, data=statuses, title='User @%s Timeline: Page %d' % (screen_name_or_short_id, page)))

  def func_me(self, page=1):
    self.func_timeline(page=page)

  def func_fav(self, short_id_or_page=None):
    if not short_id_or_page:
      short_id_or_page = '1'
    if short_id_or_page.isdigit():
      try:
        page = int(short_id_or_page)
      except ValueError:
        return u'Unknown page number: %s.' % short_id_or_page
      statuses = self._api.get_favorites(page=page)
      self._queue.put(Job(self._jid, data=statuses, title='Favourite: Page %d' % page))
    else:
      long_id, long_id_type = self._util.restore_short_id(short_id_or_page)
      if long_id_type == db.TYPE_DM:
        raise TypeError('Can not create a direct message as favourite.')
      self._api.create_favorite(long_id)
      return u'Created %s to favourites.' % str(short_id_or_page)

  def func_unfav(self, short_id):
    long_id, long_id_type = self._util.restore_short_id(short_id)
    if long_id_type == db.TYPE_DM:
      raise TypeError('Can not delete a direct message as favourite.')
    self._api.destroy_favorite(long_id)
    return u'Deleted %s from favourites.' % str(short_id)

  def func_reply(self, short_id_or_page=None, *content):
    if not content:
      try:
        page = int(short_id_or_page) if short_id_or_page else 1
      except ValueError:
        return u'Unknown page number %s.' % short_id_or_page
      statuses = self._api.get_mentions(page=page)
      self._queue.put(Job(self._jid, data=statuses, title='Mentions: Page %d' % page))
    else:
      long_id, long_id_type = self._util.restore_short_id(short_id_or_page)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        screen_name = status['user']['screen_name']
      else:
        direct_message = self._api.get_direct_message(long_id)
        screen_name = direct_message['sender_screen_name']
        long_id = None
      message = u'@%s %s' % (screen_name, ' '.join(content))
      status = self._api.post_update(message.encode('UTF8'), long_id)
      self._queue.put(Job(self._jid, data=status, allow_duplicate=False))

  def func_replyall(self, short_ids, *content):
    def add_mention_user(screen_name):
      if screen_name not in mention_users and screen_name != self._user['screen_name']:
        mention_users.append(screen_name)

    first_long_id = None
    mention_users = list()
    for short_id in short_ids.split(','):
      long_id, long_id_type = self._util.restore_short_id(short_id)
      try:
        if long_id_type == db.TYPE_STATUS:
          if first_long_id is None:
            first_long_id = long_id
          data = self._api.get_status(long_id)
          add_mention_user(data['user']['screen_name'])
        else:
          data = self._api.get_direct_message(long_id)
          add_mention_user(data['sender_screen_name'])
        user_mentions = data.get('entities', dict()).get('user_mentions', ())
        for x in user_mentions:
          add_mention_user(x['screen_name'])
      except twitter.NotFoundError:
        pass
    if not mention_users:
      raise twitter.NotFoundError('Not found.')
    message = u'%s %s' % (' '.join('@' + x for x in mention_users), ' '.join(content))
    status = self._api.post_update(message.encode('UTF8'), first_long_id)
    self._queue.put(Job(self._jid, data=status, allow_duplicate=False))

  def func_rt(self, short_id, *content):
    long_id, long_id_type = self._util.restore_short_id(short_id)
    if long_id_type == db.TYPE_DM:
      raise TypeError('Can not retweet a direct message.')
    if not content:
      status = self._api.create_retweet(long_id)
      self._queue.put(Job(self._jid, data=status, allow_duplicate=False))
    else:
      status = self._api.get_status(long_id)
      user_msg = ' '.join(content)
      if user_msg and ord(user_msg[-1]) < 128:
        user_msg += ' '
      if 'retweeted_status' in status:
        status = status['retweeted_status']
      message = u'%sRT @%s' % (user_msg, status['user']['screen_name'])
      if len(message) > twitter.CHARACTER_LIMIT:
        raise ValueError('Content is too long to be RT.')
      else:
        message = '%s: %s' % (message, status['text'])
        message = message[:140]
      status = self._api.post_update(message.encode('UTF8'))
      self._queue.put(Job(self._jid, data=status, allow_duplicate=False))

  def func_del(self, short_id=None):
    if not short_id:
      statuses = self._api.get_user_timeline(screen_name=self._user['screen_name'], count=1)
      if statuses:
        long_id = statuses[0]['id_str']
        long_id_type = db.TYPE_STATUS
      else:
        raise twitter.NotFoundError
    else:
      long_id, long_id_type = self._util.restore_short_id(short_id)
    if long_id_type == db.TYPE_STATUS:
      status = self._api.destroy_status(long_id)
      return u'Status deleted: %s' % self._util.parse_text(status)
    else:
      dm = self._api.destroy_direct_message(long_id)
      return u'Direct message to %s deleted: %s' % (dm['recipient_screen_name'], self._util.parse_text(dm))

  def func_dm(self, screen_name_or_short_id_or_page='', *content):
    if not content:
      try:
        page = int(screen_name_or_short_id_or_page) if screen_name_or_short_id_or_page else 1
      except ValueError:
        return u'Unknown page number: %s.' % screen_name_or_short_id_or_page
      statuses = self._api.get_direct_messages(page=page)
      self._queue.put(Job(self._jid, data=statuses, title='Direct Messages: Page %s' % page))
    else:
      if screen_name_or_short_id_or_page and screen_name_or_short_id_or_page[0] == '#':
        long_id, long_id_type = self._util.restore_short_id(screen_name_or_short_id_or_page)
        if long_id_type == db.TYPE_STATUS:
          status = self._api.get_status(long_id)
          screen_name = status['user']['screen_name']
        else:
          direct_message = self._api.get_direct_message(long_id)
          screen_name = direct_message['sender']['screen_name']
      else:
        screen_name = screen_name_or_short_id_or_page
      message = ' '.join(content)
      dm = self._api.post_direct_message(screen_name.encode('UTF8'), message.encode('UTF8'))
      self._queue.put(Job(self._jid, title='Direct Message sent to %s:' % screen_name, data=dm, allow_duplicate=False))


  def func_msg(self, short_id_or_long_id):
    long_id, long_id_type = self._util.restore_short_id(short_id_or_long_id)
    long_id_str = str(long_id)
    data = list()
    if long_id_type == db.TYPE_STATUS:
      origin_status = self._api.get_status(long_id)
      related_result = self._api.get_related_results(long_id)
      if related_result:
        last_conversation_role = 'Ancestor' # possible value: Ancestor, Descendant, Fork
        related_result = related_result[0]['results']
        for result in related_result:
          if result['kind'] == 'Tweet':
            if result['annotations']['ConversationRole'] != last_conversation_role:
              data.append(origin_status)
              origin_status = None
              last_conversation_role = result['annotations']['ConversationRole']
            data.append(result['value'])
      if origin_status:
        data.append(origin_status)
      first_short = data[0]['id_str'] == long_id
      while len(data) <= MAX_CONVERSATION_NUM or first_short:
        first_short = False
        status = data[0]
        if status['in_reply_to_status_id_str']:
          long_id = status['in_reply_to_status_id_str']
          try:
            status = self._api.get_status(long_id)
          except twitter.Error:
            break
        else:
          break
        if 'retweeted_status' in status:
          data.insert(0, status['retweeted_status'])
        else:
          data.insert(0, status)
    else:
      long_id_str = ''
      all_dms = self._api.get_direct_messages(max_id=long_id, count=50)
      if all_dms and all_dms[0]['id_str'] == str(long_id):
        all_dms.extend(self._api.get_sent_direct_messages(max_id=long_id, count=50))
        for dm in ifilter(lambda dm: dm['recipient_screen_name'] == self._user['screen_name'] or
                                     dm['sender_screen_name'] == self._user['screen_name'], sorted(all_dms, key=operator.itemgetter('id'), reverse=True)):
          data.insert(0, dm)
          if len(data) >= MAX_CONVERSATION_NUM:
            break
      else:
        raise twitter.NotFoundError
    self._queue.put(Job(self._jid, data=data, title='Conversation: %s' % long_id_str, reverse=False))

  def func_block(self, screen_name):
    if screen_name[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(screen_name)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        screen_name = status['user']['screen_name']
      else:
        direct_message = self._api.get_direct_message(long_id)
        screen_name = direct_message['sender_screen_name']
    self._api.create_block(screen_name)
    return u'Blocked %s.' % screen_name

  def func_unblock(self, screen_name):
    if screen_name[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(screen_name)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        screen_name = status['user']['screen_name']
      else:
        direct_message = self._api.get_direct_message(long_id)
        screen_name = direct_message['sender_screen_name']
    self._api.destroy_block(screen_name)
    return u'Delete %s from blocked.' % screen_name

  def func_spam(self, screen_name):
    if screen_name[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(screen_name)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        screen_name = status['user']['screen_name']
      else:
        direct_message = self._api.get_direct_message(long_id)
        screen_name = direct_message['sender_screen_name']
    self._api.report_spam(screen_name)
    return u'Reported %s as spam.' % screen_name

  def func_follow(self, screen_name):
    if screen_name[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(screen_name)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        screen_name = status['user']['screen_name']
      else:
        direct_message = self._api.get_direct_message(long_id)
        screen_name = direct_message['sender_screen_name']
    twitter_user = self._api.create_friendship(screen_name)
    if twitter_user.get('protected') and twitter_user.get('follow_request_sent'):
      return u'Have sent follow request to %s' % screen_name
    else:
      return u'Following %s.' % screen_name

  def func_unfollow(self, screen_name):
    if screen_name[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(screen_name)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        screen_name = status['user']['screen_name']
      else:
        direct_message = self._api.get_direct_message(long_id)
        screen_name = direct_message['sender_screen_name']
    self._api.destroy_friendship(screen_name)
    return u'Unfollowed %s.' % screen_name

  def func_if(self, user_a, user_b=None):
    if user_b is None:
      user_b = self._user['screen_name']
    result = self._api.exists_friendship(user_a=user_a, user_b=user_b)
    if result:
      return u'%s is already following %s.' % (user_a, user_b)
    else:
      return u'%s is not following %s yet.' % (user_a, user_b)

  def func_on(self, *args):
    if args:
      for a in args:
        a = a.lower()
        if a == 'home':
          self._user['timeline'] |= db.MODE_HOME
        elif a == 'mention':
          self._user['timeline'] |= db.MODE_MENTION
        elif a == 'dm':
          self._user['timeline'] |= db.MODE_DM
        elif a == 'list':
          self._user['timeline'] |= db.MODE_LIST
        elif a == 'event':
          self._user['timeline'] |= db.MODE_EVENT
        elif a == 'track':
          self._user['timeline'] |= db.MODE_TRACK
      self._xmpp.stream_threads[self._bare_jid].user_changed()
      db.update_user(id=self._user['id'], timeline=self._user['timeline'])
    modes = []
    if self._user['timeline'] & db.MODE_LIST:
      modes.append('list')
    if self._user['timeline'] & db.MODE_HOME:
      modes.append('home')
    if self._user['timeline'] & db.MODE_MENTION:
      modes.append('mention')
    if self._user['timeline'] & db.MODE_DM:
      modes.append('dm')
    if self._user['timeline'] & db.MODE_EVENT:
      modes.append('event')
    if self._user['timeline'] & db.MODE_TRACK:
      modes.append('track')
    modes_str = ', '.join(modes) if modes else 'nothing'
    return u'You have enabled update for %s.' % modes_str

  def func_off(self, *args):
    if args:
      for a in args:
        a = a.lower()
        if a == 'home':
          self._user['timeline'] &= ~db.MODE_HOME
        elif a == 'mention':
          self._user['timeline'] &= ~db.MODE_MENTION
        elif a == 'dm':
          self._user['timeline'] &= ~db.MODE_DM
        elif a == 'list':
          self._user['timeline'] &= ~db.MODE_LIST
        elif a == 'event':
          self._user['timeline'] &= ~db.MODE_EVENT
        elif a == 'track':
          self._user['timeline'] &= ~db.MODE_TRACK
    else:
      self._user['timeline'] = db.MODE_NONE
    db.update_user(self._user['id'], timeline=self._user['timeline'])
    self._xmpp.stream_threads[self._bare_jid].user_changed()
    return self.func_on()

  def func_live(self, list_user_name=None):
    if list_user_name:
      path = list_user_name.split('/', 1)
      if len(path) == 1:
        list_user = self._user['screen_name']
        list_name = path[0]
      else:
        list_user, list_name = path
      response = self._api.get_list(list_user.encode('UTF8'), list_name.encode('UTF8'))
      self._user['list_user'] = response['user']['screen_name']
      self._user['list_name'] = response['slug']
      db.update_user(id=self._user['id'], list_user=self._user['list_user'], list_name=self._user['list_name'],
        list_ids=None, list_ids_last_update=0)
      self._xmpp.stream_threads[self._bare_jid].user_changed()
    if self._user['list_user'] and self._user['list_name']:
      return u'List update is assigned for %s/%s.' % (self._user['list_user'], self._user['list_name'])
    return u'Please specify a list as screen_name/list_name format first.'

  def func_msgtpl(self, *content):
    content = ' '.join(content)
    if content:
      if content.lower() == 'reset':
        content = None
        result = u'You have reset message template to default. Preview:\n%s'
      else:
        result = u'You have updated message template. Preview:\n%s'
      self._user['msg_tpl'] = content
      db.update_user(id=self._user['id'], msg_tpl=content)
      test_single = twitter.Status({u'favorited': False, u'contributors': None, u'truncated': False,
                                    u'text': u'RT @TwiOtaku: @gh05tw01f Welcome! Wish you enjoy!',
                                    u'in_reply_to_status_id': None,
                                    u'user': {u'utc_offset': 28800, u'id_str': u'8104012', u'statuses_count': 25890,
                                              u'follow_request_sent': False, u'friends_count': 393,
                                              u'profile_use_background_image': True, u'contributors_enabled': False,
                                              u'profile_link_color': u'0099B9',
                                              u'profile_image_url': u'http://a2.twimg.com/profile_images/1470742579/avatar_normal.PNG'
                                      , u'notifications': False, u'show_all_inline_media': True,
                                              u'profile_background_image_url_https': u'https://si0.twimg.com/images/themes/theme4/bg.gif'
                                      , u'profile_background_color': u'0099B9', u'id': 8104012,
                                              u'profile_background_image_url': u'http://a1.twimg.com/images/themes/theme4/bg.gif'
                                      ,
                                              u'description': u'\u5916\u8868\u5927\u53d4\u7684\u706b\u661f\u8179\u9ed1\u6b63\u592a\u3002\u80bf\u7624\u79d1\u533b\u5b66\u751f\u3002\u8bfa\u57fa\u4e9aE71\u4f7f\u7528\u8005\u3002\u7231\u751f\u6d3b\u7231\u5410\u69fd\u3002\u4eb2\u65e5\u6d3e\uff0c\u4eb2\u817e\u8baf\uff0c\u4e2d\u533b\u9ed1\uff0c\u4e0d\u559c\u52ff\u6270\u3002\u57fa\u7763\u5f92\u3002\u76ee\u524d\u4ee5\u751f\u6d3b\u63a8\u3001\u719f\u4eba\u63a8\u4e3a\u4e3b\uff0c\u6280\u672f\u63a8\u548c\u533b\u5b66\u63a8\u6781\u5c11\u6570\u3002'
                                      , u'lang': u'en', u'default_profile': False, u'profile_background_tile': False,
                                              u'profile_sidebar_border_color': u'5ED4DC', u'verified': False,
                                              u'screen_name': u'gh05tw01f', u'url': u'http://www.cnblogs.com/ayanamist/'
                                      , u'following': True,
                                              u'profile_image_url_https': u'https://si0.twimg.com/profile_images/1470742579/avatar_normal.PNG'
                                      , u'profile_sidebar_fill_color': u'95E8EC', u'time_zone': u'Beijing',
                                              u'name': u'ayanamist', u'geo_enabled': True,
                                              u'profile_text_color': u'3C3940', u'followers_count': 876,
                                              u'protected': False, u'location': u'Wuhan, China',
                                              u'default_profile_image': False, u'is_translator': False,
                                              u'favourites_count': 47, u'created_at': u'Fri Aug 10 13:52:07 +0000 2007',
                                              u'listed_count': 53}, u'geo': None, u'id': 115061633151279104L,
                                    u'source': u'<a href="http://code.google.com/p/twiotaku/" rel="nofollow">TwiOtaku</a>'
        , u'created_at': u'Sat Sep 17 13:56:45 +0000 2011', u'retweeted': False, u'coordinates': None,
                                    u'in_reply_to_user_id_str': None, u'entities': {u'user_mentions': [
            {u'indices': [3, 12], u'screen_name': u'TwiOtaku', u'id': 250488521, u'name': u'TwiOtaku',
             u'id_str': u'250488521'},
            {u'indices': [14, 24], u'screen_name': u'gh05tw01f', u'id': 8104012, u'name': u'ayanamist',
             u'id_str': u'8104012'}], u'hashtags': [], u'urls': []}, u'in_reply_to_status_id_str': None,
                                    u'in_reply_to_screen_name': None, u'in_reply_to_user_id': None, u'place': None,
                                    u'retweet_count': 0, u'id_str': u'115061633151279104'})
      test_single['retweeted_status'] = twitter.Status({u'favorited': False, u'contributors': None, u'truncated': False,
                                                        u'text': u'@gh05tw01f Welcome! Wish you enjoy!',
                                                        u'in_reply_to_status_id': 115061186621476864L,
                                                        u'user': {u'utc_offset': 28800, u'id_str': u'250488521',
                                                                  u'statuses_count': 3, u'follow_request_sent': False,
                                                                  u'friends_count': 1,
                                                                  u'profile_use_background_image': True,
                                                                  u'contributors_enabled': False,
                                                                  u'profile_link_color': u'0084B4',
                                                                  u'profile_image_url': u'http://a3.twimg.com/profile_images/1240928412/otaku_normal.png'
                                                          , u'notifications': False, u'show_all_inline_media': True,
                                                                  u'profile_background_image_url_https': u'https://si0.twimg.com/images/themes/theme1/bg.png'
                                                          , u'profile_background_color': u'C0DEED', u'id': 250488521,
                                                                  u'profile_background_image_url': u'http://a0.twimg.com/images/themes/theme1/bg.png'
                                                          ,
                                                                  u'description': u'TwiOtaku is a GTalk based Twitter client using Twitter Streaming API written by @gh05tw01f .'
                                                          , u'lang': u'en', u'default_profile': True,
                                                                  u'profile_background_tile': False,
                                                                  u'profile_sidebar_border_color': u'C0DEED',
                                                                  u'verified': False, u'screen_name': u'TwiOtaku',
                                                                  u'url': u'http://code.google.com/p/twiotaku/',
                                                                  u'following': False,
                                                                  u'profile_image_url_https': u'https://si0.twimg.com/profile_images/1240928412/otaku_normal.png'
                                                          , u'profile_sidebar_fill_color': u'DDEEF6',
                                                                  u'time_zone': u'Chongqing', u'name': u'TwiOtaku',
                                                                  u'geo_enabled': False,
                                                                  u'profile_text_color': u'333333',
                                                                  u'followers_count': 13, u'protected': False,
                                                                  u'location': u'China', u'default_profile_image': False
                                                          , u'is_translator': False, u'favourites_count': 0,
                                                                  u'created_at': u'Fri Feb 11 05:30:20 +0000 2011',
                                                                  u'listed_count': 0}, u'geo': None,
                                                        u'in_reply_to_user_id_str': u'8104012',
                                                        u'source': u'<a href="http://code.google.com/p/twiotaku/" rel="nofollow">TwiOtaku</a>'
        , u'created_at': u'Sat Sep 17 13:55:53 +0000 2011', u'retweeted': False, u'coordinates': None,
                                                        u'id': 115061412182761472L, u'entities': {u'user_mentions': [
            {u'indices': [0, 10], u'screen_name': u'gh05tw01f', u'id': 8104012, u'name': u'ayanamist',
             u'id_str': u'8104012'}], u'hashtags': [], u'urls': []}, u'in_reply_to_status_id_str': u'115061186621476864'
        , u'in_reply_to_screen_name': u'gh05tw01f', u'id_str': u'115061412182761472', u'place': None,
                                                        u'retweet_count': 0, u'in_reply_to_user_id': 8104012})
      test_single['retweeted_status']['in_reply_to_status'] = twitter.Status(
          {u'favorited': False, u'entities': {u'user_mentions': [], u'hashtags': [], u'urls': []}, u'contributors': None
          , u'truncated': False, u'text': u'Hello from TwiOtaku!', u'created_at': u'Sat Sep 17 13:54:59 +0000 2011',
           u'retweeted': False, u'in_reply_to_status_id_str': None, u'coordinates': None,
           u'in_reply_to_user_id_str': None,
           u'source': u'<a href="http://code.google.com/p/twiotaku/" rel="nofollow">TwiOtaku</a>',
           u'in_reply_to_status_id': None, u'id_str': u'115061186621476864', u'in_reply_to_screen_name': None,
           u'user': {u'utc_offset': 28800, u'id_str': u'8104012', u'statuses_count': 25890,
                     u'follow_request_sent': False, u'friends_count': 393, u'profile_use_background_image': True,
                     u'contributors_enabled': False, u'profile_link_color': u'0099B9',
                     u'profile_image_url': u'http://a2.twimg.com/profile_images/1470742579/avatar_normal.PNG',
                     u'notifications': False, u'show_all_inline_media': True,
                     u'profile_background_image_url_https': u'https://si0.twimg.com/images/themes/theme4/bg.gif',
                     u'profile_background_color': u'0099B9', u'id': 8104012,
                     u'profile_background_image_url': u'http://a1.twimg.com/images/themes/theme4/bg.gif',
                     u'description': u'\u5916\u8868\u5927\u53d4\u7684\u706b\u661f\u8179\u9ed1\u6b63\u592a\u3002\u80bf\u7624\u79d1\u533b\u5b66\u751f\u3002\u8bfa\u57fa\u4e9aE71\u4f7f\u7528\u8005\u3002\u7231\u751f\u6d3b\u7231\u5410\u69fd\u3002\u4eb2\u65e5\u6d3e\uff0c\u4eb2\u817e\u8baf\uff0c\u4e2d\u533b\u9ed1\uff0c\u4e0d\u559c\u52ff\u6270\u3002\u57fa\u7763\u5f92\u3002\u76ee\u524d\u4ee5\u751f\u6d3b\u63a8\u3001\u719f\u4eba\u63a8\u4e3a\u4e3b\uff0c\u6280\u672f\u63a8\u548c\u533b\u5b66\u63a8\u6781\u5c11\u6570\u3002'
             , u'lang': u'en', u'default_profile': False, u'profile_background_tile': False,
                     u'profile_sidebar_border_color': u'5ED4DC', u'verified': False, u'screen_name': u'gh05tw01f',
                     u'url': u'http://www.cnblogs.com/ayanamist/', u'following': True,
                     u'profile_image_url_https': u'https://si0.twimg.com/profile_images/1470742579/avatar_normal.PNG',
                     u'profile_sidebar_fill_color': u'95E8EC', u'time_zone': u'Beijing', u'name': u'ayanamist',
                     u'geo_enabled': True, u'profile_text_color': u'3C3940', u'followers_count': 876,
                     u'protected': False, u'location': u'Wuhan, China', u'default_profile_image': False,
                     u'is_translator': False, u'favourites_count': 47, u'created_at': u'Fri Aug 10 13:52:07 +0000 2007',
                     u'listed_count': 53}, u'place': None, u'retweet_count': 0, u'geo': None, u'id': 115061186621476864L
          , u'in_reply_to_user_id': None})
      self._util = Util(self._user)
      preview = self._util.parse_status(test_single)
      result %= preview
    else:
      if self._user['msg_tpl']:
        result = u'Your current message template is:\n%s' % self._user['msg_tpl']
      else:
        result = u'Your current message template is default'
    return result

  def func_datefmt(self, *content):
    content = ' '.join(content)
    if content:
      if content.lower() == 'reset':
        content = None
        result = u'You have reset date format to default.'
      else:
        now = datetime.now()
        now_str = now.strftime(content.encode('UTF8')).decode('UTF8')
        result = u'You have updated date format as following: %s\nPreview: %s' % (content, now_str)
      db.update_user(id=self._user['id'], date_fmt=content)
    else:
      if self._user['date_fmt']:
        result = u'Your current date format is: %s.' % self._user['date_fmt']
      else:
        result = u'Your current date format is default.'
    return result

  def func_always(self, value=None):
    if value is not None:
      value = value.lower()
      if value in ('true', '1', 'on'):
        value = 1
      elif value in ('false', '0', 'off'):
        value = 0
      else:
        raise TypeError('Only accept true/false, 1/0, on/off.')
      self._user['always'] = value
      db.update_user(id=self._user['id'], always=value)
    if self._user['always']:
      return u'You will always receive updates no matter you are online or not.'
    else:
      return u'You will only receive updates when your status is available.'

  def func_track(self, *values):
    if values:
      self._user['track_words'] = ','.join(values)
      db.update_user(id=self._user['id'], track_word=self._user['track_words'])
      self._xmpp.stream_threads[self._bare_jid].stop()
      self._xmpp.stream_threads[self._bare_jid].join()
      self._xmpp.start_stream(self._bare_jid)
    return u'You are tracking words: %s. (comma seprated)' % self._user['track_words']

  def func_help(self):
    return u'Please refer to following url to get more help.\nhttp://code.google.com/p/twiotaku/wiki/CommandsReferrence'