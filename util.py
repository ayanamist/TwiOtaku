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

class ostring(object):
  def __init__(self, s):
    self.original_s = s
    self._str_list = list()
    self._str_indices = list()

  def __unicode__(self):
    if self._str_indices:
      str_indices = list()
      str_indices.append(0)
      str_indices.extend(self._str_indices)
      result = list()
      for i, s in enumerate(self._str_list):
        result.append(self.original_s[str_indices[i * 2]:str_indices[i * 2 + 1]])
        result.append(s)
      result.append(self.original_s[str_indices[-1]:-1])
      return u''.join(result)
    else:
      return unicode(self.original_s)

  def replace_indices(self, start, stop, replace_text):
    if not self._str_indices:
      self._str_indices.append(start)
      self._str_indices.append(stop)
      self._str_list.append(replace_text)
      return self
    else:
      for i in range(len(self._str_list)):
        if start > self._str_indices[i * 2]:
          self._str_indices.insert(i * 2 + 2, start)
          self._str_indices.insert(i * 2 + 3, stop)
          self._str_list.insert(i + 1, replace_text)
          return self
      # start is smaller than any of pairs in the list, we should add them to the first.
      self._str_indices.insert(0, start)
      self._str_indices.insert(1, stop)
      self._str_list.insert(0, replace_text)
      return self

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
    msg_dict['content'] = single['text']
    if 'entities' in single:
      tmp = ostring(msg_dict['content'])
      if 'urls' in single['entities']:
        for url in single['entities']['urls']:
          if url['expanded_url']:
            tmp.replace_indices(url['indices'][0], url['indices'][1], url['expanded_url'])
      if 'media' in single['entities']:
        for media in single['entities']['media']:
          if media['media_url']:
            tmp.replace_indices(media['indices'][0], media['indices'][1], media['media_url'])
      msg_dict['content'] = unicode(tmp)
    msg_dict['content'] = Util.parse_text(msg_dict['content'])
    if isinstance(single, twitter.Status):
      if single['user']['utc_offset']:
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
      if 'in_reply_to_status' in single and isinstance(single['in_reply_to_status'], twitter.Status):
        old_allow_duplicate = self.allow_duplicate
        self.allow_duplicate = True
        in_reply_to_text = self.parse_single(retweeted_status)
        self.allow_duplicate = old_allow_duplicate
        text +='\n┌────────────\n%s\n└────────────' % in_reply_to_text
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
      if isinstance(data, list):
        if reverse:
          data.reverse()
        for single in data:
          try:
            text = self.parse_single(single)
            if text:
              msgs.append(text)
          except (TypeError, DuplicateError):
            pass
      else:
        try:
          text = self.parse_single(data)
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
      return short_id, db.TYPE_STATUS