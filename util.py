#!/usr/bin/python
import re
from time import mktime, localtime, strftime
from email.utils import parsedate
from xml.sax.saxutils import unescape

import db
import twitter
from config import MAX_ID_LIST_NUM

class DuplicateError(Exception):
  pass


class Util(object):
  allow_duplicate = True


  def __init__(self, user):
    self._user = user

  @staticmethod
  def parse_text(text):
    return unescape(text).replace('\r\n', '\n').replace('\r', '\n')

  def parse_single(self, single):
    if single is None:
      return None
    msg_dict = dict()
    short_id, short_id_alpha = self.generate_short_id(single)
    msg_dict['id_str'] = single['id_str']
    msg_dict['shortid'] = '#%s=%s' % (short_id, short_id_alpha)
    t = mktime(parsedate(single['created_at']))
    msg_dict['content'] = Util.parse_text(single['text'])
    if isinstance(single, twitter.Status):
      t += single['user']['utc_offset']
      msg_dict['time'] = strftime('%Y-%m-%d %H:%M:%S', localtime(t))
      msg_dict['username'] = single['user']['screen_name']
      source = re.match(r'<a .*>(.*)</a>', single['source'])
      msg_dict['source'] = source.group(1) if source else single['source']
      retweeted_status = single.get('retweeted_status')
      if retweeted_status is not None:
        old_allow_duplicate = self.allow_duplicate
        self.allow_duplicate = True
        msg_dict['content'] = self.parse_single(retweeted_status)
        self.allow_duplicate = old_allow_duplicate
        text = '%(content)s\nRetweeted by %(username)s %(time)s [%(id_str)s%(shortid)s] via %(source)s' % msg_dict
      else:
        text = '%(username)s: %(content)s\n%(time)s [%(id_str)s%(shortid)s] via %(source)s' % msg_dict
    elif isinstance(single, twitter.DirectMessage):
      msg_dict['username'] = single['sender']['screen_name']
      t += single['sender']['utc_offset']
      msg_dict['time'] = strftime('%Y-%m-%d %H:%M:%S', localtime(t))
      text = 'Direct Message:\n%(username)s: %(content)s\n%(time)s [%(id_str)s%(shortid)s]' % msg_dict
    else:
      raise TypeError('Not a valid Status or Direct Message.')
    return text

  def parse_data(self, data, reverse=True):
    if data:
      msgs = list()
      if reverse:
        data.reverse()
      for single in data:
        try:
          text = self.parse_single(single)
          if text:
            msgs.append(text)
        except (TypeError, DuplicateError):
          pass
      return msgs


  def generate_short_id(self, single):
    def digit_to_alpha(digit):
      if not isinstance(digit, int):
        raise TypeError('Only accept digit argument.')
      nums = list()
      while digit >= 26:
        nums.insert(0, digit % 26)
        digit //= 26
      nums.insert(0, digit)
      nums[-1] += 1
      return ''.join([chr(x + 64) for x in nums])

    if isinstance(single, twitter.Status):
      single_type = db.TYPE_STATUS
    else:
      single_type = db.TYPE_DM
    long_id = single['id_str']
    short_id = db.get_short_id_from_long_id(self._user['id'], long_id, single_type)
    if short_id is not None:
      if not self.allow_duplicate:
        raise DuplicateError
    else:
      self._user['id_list_ptr'] += 1
      short_id = self._user['id_list_ptr']
      if short_id >= MAX_ID_LIST_NUM:
        short_id = self._user['id_list_ptr'] = 0
      db.update_user(id=self._user['id'], id_list_ptr=short_id)
      db.update_long_id_from_short_id(self._user['id'], short_id, long_id, single_type)
    return short_id, digit_to_alpha(short_id)

  def restore_short_id(self, short_id):
    def alpha_to_digit(alpha):
      if not (isinstance(alpha, str) and alpha.isalpha):
        raise TypeError('Only accept alpha argument.')
      return reduce(lambda x, y: x * 26 + y, [ord(x) - 64 for x in alpha]) - 1

    short_id_regex = r'^(?:#)?([A-Z]+|\d+)$'
    short_id = str(short_id).upper()
    m = re.match(short_id_regex, short_id)
    if m is None:
      raise ValueError
    g = m.group(1)
    try:
      short_id = int(g)
    except ValueError:
      short_id = alpha_to_digit(short_id)
    if short_id < MAX_ID_LIST_NUM:
      return db.get_long_id_from_short_id(self._user['id'], short_id)
    else:
      return short_id, None