import random
import time
import operator
from Queue import Queue
from urlparse import parse_qsl
from email.utils import parsedate

import db
from config import OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET, MAX_CONVERSATION_NUM, ADMIN_USERS
from worker import Job
from lib import oauth, twitter
from lib.util import Util
from lib.decorators import debug

SHORT_COMMANDS = {
  '@': 'reply',
  'r': 'reply',
  'd': 'dm',
  'ra': 'replyall',
  're': 'retweet',
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

  @debug('xmpp')
  def process(self, msg):
    self._jid = str(msg['from'])
    self._bare_jid = self._xmpp.getjidbare(self._jid).lower()
    self._queue = self._xmpp.worker_queues.get(self._bare_jid, Queue())
    self._user = db.get_user_from_jid(self._bare_jid)
    self._util = Util(self._user)
    self._api = twitter.Api(consumer_key=OAUTH_CONSUMER_KEY, consumer_secret=OAUTH_CONSUMER_SECRET,
      access_token_key=self._user.get('access_key'), access_token_secret=self._user.get('access_secret'))
    try:
      result = self.parse_command(msg['body'].rstrip())
    except (twitter.TwitterError, TypeError, ValueError), e:
      result = unicode(e)
    if result:
      msg.reply(result).send()

  def parse_command(self, cmd):
    if cmd[0] == '-' or cmd[0] == ' ':
      args = cmd[1:].split(' ')
      if args[0] in SHORT_COMMANDS:
        args[0] = SHORT_COMMANDS[args[0]]
      if not self._user and args[0] != 'invite':
        return
      func_name = 'func_' + args[0]
      if func_name in dir(self):
        func = getattr(self, func_name)
      else:
        return 'Invalid command.'
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
      return 'Please visit below url to get PIN code:\n%s\nthen you should use "-bind PIN" command to actually bind your Twitter.' % redirect_url
    else:
      return 'Network error.'

  def func_bind(self, pin_code):
    if self._user['access_key']:
      token = oauth.Token(self._user['access_key'])
      if type(pin_code) is unicode:
        pin_code = pin_code.encode('UTF8')
      token.set_verifier(pin_code)
      consumer = oauth.Consumer(OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET)
      client = oauth.Client(consumer, token)
      resp = client.request(twitter.ACCESS_TOKEN_URL, "POST")
      access_token = dict(parse_qsl(resp))
      if 'oauth_token' in access_token:
        db.update_user(self._user['id'], access_key=access_token['oauth_token'],
          access_secret=access_token['oauth_token_secret'],
          screen_name=access_token['screen_name'])
        self._xmpp.add_online_user(self._bare_jid)
        return 'Associated you with @%s.' % access_token['screen_name']
    return 'Invalid PIN code.'

  def func_invite(self, invite_code=None):
    def generate_invite_code():
      valid_chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
      return ''.join(random.choice(valid_chars) for _ in range(8))

    expire_days = 3

    if invite_code:
      invite_code, create_time = db.get_invite_code(invite_code)
      if invite_code and create_time and create_time + expire_days * 24 * 3600 > time.time():
        db.delete_invite_code(invite_code)
        if not self._user:
          db.add_user(self._bare_jid)
        return 'Your account %s has been added, enjoy using TwiOtaku.' % self._bare_jid
      else:
        return 'Invite code is invalid or expired.'

    elif self._bare_jid in ADMIN_USERS:
      invite_code = generate_invite_code()
      create_time = int(time.time())
      db.add_invite_code(invite_code, create_time)
      return 'You have generated a new invite code which is available for %d days: %s' % (expire_days, invite_code)

  def func_user(self, screen_name=None):
    if screen_name and screen_name[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(screen_name)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        twitter_user = status['user']
      else:
        direct_message = self._api.get_direct_message(long_id)
        twitter_user = direct_message['sender']
    else:
      if screen_name is None:
        screen_name = self._user['screen_name']
      twitter_user = self._api.get_user(screen_name=screen_name)
    texts = ['User @%s (%s):' % (twitter_user['screen_name'], twitter_user['name'])]
    follow_str = ''
    if twitter_user['protected']:
      follow_str = 'Protected user. '
    if twitter_user['following']:
      follow_str += 'You are following.'
    else:
      if twitter_user['follow_request_sent']:
        follow_str += 'You have sent follow request.'
      else:
        follow_str += 'You are not following.'
    texts.append(follow_str)
    avatar_url = twitter_user['profile_image_url_https']
    i = avatar_url.rfind('_normal.')
    if i != -1:
      avatar_url = avatar_url[:i] + avatar_url[i + 7:]
    texts.append('Avatar: %s' % avatar_url)
    if twitter_user['url']:
      texts.append('Web: %s' % twitter_user['url'])
    if twitter_user['location']:
      texts.append('Location: %s' % twitter_user['location'])
    texts.append('Following: %d' % twitter_user['friends_count'])
    texts.append('Followers: %d' % twitter_user['followers_count'])
    texts.append('Tweets: %d' % twitter_user['statuses_count'])
    join_time = time.mktime(parsedate(twitter_user['created_at']))
    if twitter_user['utc_offset']:
      join_time += twitter_user['utc_offset']
    join_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(join_time))
    texts.append('Joined at: %s' % join_time)
    texts.append('Tweets per day: %.2f' % (twitter_user['statuses_count'] * 86400 /
                                           (time.time() - time.mktime(parsedate(twitter_user['created_at'])))))
    if twitter_user['description']:
      texts.append('Bio: %s' % twitter_user['description'])
    return '\n'.join(texts)

  def func_list(self, *args):
    length = len(args)
    if not length:
      lists = self._api.get_all_lists()
      texts = list()
      for l in lists:
        texts.append('%s %s: %s' % (l['slug'] if l['user']['screen_name'] == self._user['screen_name']
                                    else '%s/%s' % (l['user']['screen_name'], l['slug']), l['mode'], l['description']))
      return 'Subscribing Lists:\n' + '\n'.join(texts)
    elif length == 1 or (length == 2 and args[1].isdigit()):
      list_user_name = args[0]
      path = list_user_name.split('/', 1)
      if len(path) == 1:
        list_user = self._user['screen_name']
        list_name = path[0]
      else:
        list_user, list_name = path
      page = int(args[1]) if length == 2 else 1
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
        texts = ['List %s/%s %s: %s' % (l['user']['screen_name'], l['slug'], l['mode'],
                                        'You are following.' if l['following'] else ''),
                 'Member Count: %d' % l['member_count'], 'Subscriber Count: %d' % l['subscriber_count'],
                 'Description: %s' % l['description']]
        return '\n'.join(texts)
      elif list_command in ('add', 'del') and 2 <= length <= 3:
        if length == 2:
          if list_command == 'add':
            self._api.create_list(args[1], public=False)
            return 'Created private list %s.' % args[1]
          else:
            self._api.destroy_list(self._user['screen_name'], args[1])
            return 'Deleted list %s.' % args[1]
        else:
          if list_command == 'add':
            self._api.create_list_member(self._user['screen_name'], args[1], args[2])
            return 'Added %s to list %s.' % (args[2], args[1])
          else:
            self._api.destroy_list_member(self._user['screen_name'], args[1], args[2])
            return 'Removed %s from list %s.' % (args[2], args[1])
      else:
        raise TypeError('Not supported list command.')

  def func_home(self, page=1):
    statuses = self._api.get_home_timeline(page=page)
    self._queue.put(Job(self._jid, data=statuses, title='Home Timeline: Page %d' % page))

  def func_timeline(self, screen_name, page=1):
    statuses = self._api.get_user_timeline(screen_name=screen_name, page=page)
    self._queue.put(Job(self._jid, data=statuses, title='User %s Timeline: Page %d' % (screen_name, page)))

  def func_me(self, page=1):
    self.func_timeline(self._user['screen_name'], page)

  def func_fav(self, short_id_or_page=1):
    if short_id_or_page and short_id_or_page[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(short_id_or_page)
      if long_id_type == db.TYPE_DM:
        raise TypeError('Can not create a direct message as favourite.')
      self._api.create_favorite(long_id)
      return 'Created %s to favourites.' % str(long_id)
    else:
      page = int(short_id_or_page)
      statuses = self._api.get_favorites(page=page)
      self._queue.put(Job(self._jid, data=statuses, title='Favourite: Page %d' % page))

  def func_unfav(self, short_id):
    long_id, long_id_type = self._util.restore_short_id(short_id)
    if long_id_type == db.TYPE_DM:
      raise TypeError('Can not delete a direct message as favourite.')
    self._api.destroy_favorite(long_id)
    return 'Deleted %s from favourites.' % str(long_id)

  def func_reply(self, short_id_or_page=None, *content):
    if not content:
      page = int(short_id_or_page) if short_id_or_page else 1
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
        if 'entities' in data and 'user_mentions' in data['entities']:
          for x in data['entities']['user_mentions']:
            add_mention_user(x['screen_name'])
      except twitter.TwitterNotFoundError:
        pass
    if not mention_users:
      raise twitter.TwitterNotFoundError
    message = u'%s %s' % (' '.join(['@' + x for x in mention_users]), ' '.join(content))
    status = self._api.post_update(message.encode('UTF8'), first_long_id)
    self._queue.put(Job(self._jid, data=status, allow_duplicate=False))

  def func_rt(self, short_id, *content):
    long_id, long_id_type = self._util.restore_short_id(short_id)
    if long_id_type == db.TYPE_STATUS:
      status = self._api.get_status(long_id)
      user_msg = ' '.join(content)
      if user_msg and ord(user_msg[-1]) < 128:
        user_msg += ' '
      message = u'%sRT @%s:%s' % (user_msg, status['user']['screen_name'], status['text'])
      status = self._api.post_update(message.encode('UTF8'), long_id)
      self._queue.put(Job(self._jid, data=status, allow_duplicate=False))
    else:
      raise TypeError('Can not RT a direct message.')

  def func_retweet(self, short_id):
    long_id, long_id_type = self._util.restore_short_id(short_id)
    if long_id_type == db.TYPE_STATUS:
      status = self._api.create_retweet(long_id)
      self._queue.put(Job(self._jid, data=status, allow_duplicate=False))
    else:
      raise TypeError('Can not retweet a direct message.')

  def func_del(self, short_id=None):
    if not short_id:
      statuses = self._api.get_user_timeline(screen_name=self._user['screen_name'], count=1)
      if statuses:
        long_id = statuses[0]['id_str']
        long_id_type = db.TYPE_STATUS
      else:
        raise twitter.TwitterNotFoundError('Not found.')
    else:
      long_id, long_id_type = self._util.restore_short_id(short_id)
    if long_id_type == db.TYPE_STATUS:
      status = self._api.destroy_status(long_id)
      return 'Status deleted: %s' % Util.parse_text(status)
    else:
      dm = self._api.destroy_direct_message(long_id)
      return 'Direct message to %s deleted: %s' % (dm['recipient_screen_name'], Util.parse_text(dm))

  def func_dm(self, screen_name_or_short_id_or_page=None, *content):
    if not content:
      page = int(screen_name_or_short_id_or_page) if screen_name_or_short_id_or_page else 1
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
      self._queue.put(Job(self._jid, data=dm, allow_duplicate=False))


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
      one_short = data[0]['id_str'] == long_id
      while len(data) <= MAX_CONVERSATION_NUM or one_short:
        one_short = False
        status = data[0]
        if status['in_reply_to_status_id_str']:
          long_id = status['in_reply_to_status_id_str']
          try:
            status = self._api.get_status(long_id)
          except (twitter.TwitterNotFoundError, twitter.TwitterForbiddenError):
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
        for dm in sorted(all_dms, key=operator.itemgetter('id'), reverse=True):
          if dm['recipient_screen_name'] == self._user['screen_name']\
          or dm['sender_screen_name'] == self._user['screen_name']:
            data.insert(0, dm)
            if len(data) >= MAX_CONVERSATION_NUM:
              break
      else:
        raise twitter.TwitterNotFoundError('Not found.')
    self._queue.put(Job(self._jid, data=data, title='Conversation: %s' % long_id_str, reverse=False))

  def func_block(self, screen_name):
    if screen_name and screen_name[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(screen_name)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        screen_name = status['user']['screen_name']
      else:
        direct_message = self._api.get_direct_message(long_id)
        screen_name = direct_message['sender_screen_name']
    self._api.create_block(screen_name)
    return 'Blocked %s.' % screen_name

  def func_unblock(self, screen_name):
    if screen_name and screen_name[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(screen_name)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        screen_name = status['user']['screen_name']
      else:
        direct_message = self._api.get_direct_message(long_id)
        screen_name = direct_message['sender_screen_name']
    self._api.destroy_block(screen_name)
    return 'Delete %s from blocked.' % screen_name

  def func_spam(self, screen_name):
    if screen_name and screen_name[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(screen_name)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        screen_name = status['user']['screen_name']
      else:
        direct_message = self._api.get_direct_message(long_id)
        screen_name = direct_message['sender_screen_name']
    self._api.report_spam(screen_name)
    return 'Reported %s as spam.' % screen_name

  def func_follow(self, screen_name):
    if screen_name and screen_name[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(screen_name)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        screen_name = status['user']['screen_name']
      else:
        direct_message = self._api.get_direct_message(long_id)
        screen_name = direct_message['sender_screen_name']
    twitter_user = self._api.create_friendship(screen_name)
    if twitter_user.get('protected') and twitter_user.get('follow_request_sent'):
      return 'Have sent follow request to %s' % screen_name
    else:
      return 'Following %s.' % screen_name

  def func_unfollow(self, screen_name):
    if screen_name and screen_name[0] == '#':
      long_id, long_id_type = self._util.restore_short_id(screen_name)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        screen_name = status['user']['screen_name']
      else:
        direct_message = self._api.get_direct_message(long_id)
        screen_name = direct_message['sender_screen_name']
    self._api.destroy_friendship(screen_name)
    return 'Unfollowed %s.' % screen_name

  def func_if(self, user_a, user_b=None):
    if user_b is None:
      user_b = self._user['screen_name']
    result = self._api.exists_friendship(user_a=user_a, user_b=user_b)
    if result:
      return '%s is already following %s.' % (user_a, user_b)
    else:
      return '%s is not following %s yet.' % (user_a, user_b)

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
    modes_str = ', '.join(modes) if modes else 'nothing'
    return 'You have enabled update for %s.' % modes_str

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
      self._user['list_id'] = response['id']
      self._user['list_name'] = response['slug']
      db.update_user(id=self._user['id'], list_user=self._user['list_user'], list_name=self._user['list_name'],
        list_id=self._user['list_id'])
    if self._user['list_user'] and self._user['list_id'] and self._user['list_name']:
      return 'List update is assigned for %s/%s.' % (self._user['list_user'], self._user['list_name'])
    return 'Please specify a list as screen_name/list_name format first.'

  def func_help(self):
    return 'Please refer to following url to get more help.\nhttp://code.google.com/p/twiotaku/wiki/CommandsReferrence'