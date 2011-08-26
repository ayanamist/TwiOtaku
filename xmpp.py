import logging

import sleekxmpp

import oauth
import db
import constant

SHORT_COMMANDS = {
  '@': 'reply',
  'r': 'reply',
  'd': 'dm',
  'ho': 'home',
  'lt': 'list',
  'tl': 'timeline',
  's': 'switch',
  'fo': 'follow',
  'unfo': 'unfollow',
  'b': 'block',
  'ub': 'unblock',
  'm': 'msg',
  'f': 'fav',
  'uf': 'unfav',
  'u': 'user',
  '?': 'help',
  'h': 'help'
}

class XMPPBot(sleekxmpp.ClientXMPP):
  def __init__(self, jid, password):
    sleekxmpp.ClientXMPP.__init__(self, jid, password)
    self.auto_authorize = True
    self.auto_subscribe = True
    self.add_event_handler('session_start', self.on_start)
    self.add_event_handler('message', self.on_message)
    self.add_event_handler('changed_status', self.on_changed_status)
    self.online_clients = dict()

  def on_start(self, event):
    self.send_presence()
    self.get_roster()

  def on_message(self, msg):
    bare_jid = msg['from']._jid.split('/')[0].lower()
    user = db.get_user_from_jid(bare_jid)
    if user:
      h = XMPPMessageHandler(user)
      try:
        result = h.parse_command(msg['body'].rstrip())
      except BaseException, e:
        result = str(e)
        import traceback
        from StringIO import StringIO

        err = StringIO()
        traceback.print_exc(file=err)
        xmpp_logger = logging.getLogger('xmpp')
        xmpp_logger.error(err.getvalue())

      if result:
        msg.reply(result).send()

  def on_changed_status(self, presence):
    bare_jid = presence['from']._jid.split('/')[0].lower()
    n = self.online_clients.get(bare_jid, 0)
    if presence['type'] == 'available':
      if n > 0:
        self.online_clients[bare_jid] = n + 1
      else:
        user = db.get_user_from_jid(bare_jid)
        if user and user['enabled'] and user['timeline']:
          self.online_clients[bare_jid] = 1
    else:
      if n > 1:
        self.online_clients[bare_jid] = n - 1
      elif n == 1:
        del self.online_clients[bare_jid]


class XMPPMessageHandler(object):
  def __init__(self, user):
    self.user = user

  def parse_command(self, cmd):
    if cmd[0] == '-' or cmd[0] == ' ':
      args = cmd[1:].split(' ')
      if args[0] in SHORT_COMMANDS:
        args[0] = SHORT_COMMANDS[args[0]]
      func_name = 'func_' + args[0]
      if func_name in dir(self):
        func = getattr(self, func_name)
      else:
        return 'Invalid command.'
      return func(*args[1:])
    else:
      pass

  def func_oauth(self):
    consumer = oauth.Consumer(constant.CONFIG['OAUTH_CONSUMER_KEY'], constant.CONFIG['OAUTH_CONSUMER_SECRET'])
    client = oauth.Client(consumer)
    resp = client.request(constant.REQUEST_TOKEN_URL)
    try:
      from urlparse import parse_qsl
    except ImportError:
      from cgi import parse_qsl
    self._request_token = dict(parse_qsl(resp))
    oauth_token = self._request_token['oauth_token']
    redirect_url = "%s?oauth_token=%s" % (constant.AUTHORIZATION_URL, oauth_token)
    db.update_user(self.user['id'], access_key=oauth_token)
    return 'Please visit below url to get PIN code:\n%s\nthen you should use "-bind PIN" command to actually bind your Twitter.' % redirect_url

  
