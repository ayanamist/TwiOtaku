#!/usr/bin/python
# -*- encoding: utf-8 -*-
import re
from time import mktime, localtime, strftime
from email.utils import parsedate
from xml.sax.saxutils import unescape

import jinja2

import db
import twitter
from config import MAX_ID_LIST_NUM, DEFAULT_MESSAGE_TEMPLATE, DEFAULT_DATE_FORMAT

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

  def __str__(self):
    return unicode(self).encode('UTF8')

  def replace_indices(self, start, stop, replace_text):
    if not self._str_indices:
      self._str_indices.append(start)
      self._str_indices.append(stop)
      self._str_list.append(replace_text)
      return self
    else:
      for i in range(len(self._str_list)):
        if start < self._str_indices[i * 2]:
          self._str_indices.insert(i * 2, start)
          self._str_indices.insert(i * 2 + 1, stop)
          self._str_list.insert(i, replace_text)
          return self
          # start is larger than any of pairs in the list, we should add them to the last.
      self._str_indices.append(start)
      self._str_indices.append(stop)
      self._str_list.append(replace_text)
      return self


class Util(object):
  allow_duplicate = True


  def __init__(self, user):
    self._user = user

  def parse_text(self, data):
    def parse_entities(data):
      if 'entities' in data:
        tmp = ostring(data['text'])
        if 'urls' in data['entities']:
          for url in data['entities']['urls']:
            if url['expanded_url']:
              tmp.replace_indices(url['indices'][0], url['indices'][1], url['expanded_url'])
        if 'media' in data['entities']:
          for media in data['entities']['media']:
            if media['media_url']:
              tmp.replace_indices(media['indices'][0], media['indices'][1], media['media_url'])
        return unicode(tmp)
      else:
        return data['text']

    data['text'] = unescape(data['text'])
    return parse_entities(data).replace('\r\n', '\n').replace('\r', '\n')

  def make_namespace(self, single, allow_duplicate=True):
    old_allow_duplicate = self.allow_duplicate
    self.allow_duplicate = allow_duplicate
    if single is None:
      return None
    short_id, short_id_alpha = self.generate_short_id(single)
    t = mktime(parsedate(single['created_at']))
    if isinstance(single, twitter.DirectMessage):
      if single['sender']['utc_offset']:
        t += single['sender']['utc_offset']
    else:
      if single['user']['utc_offset']:
        t += single['user']['utc_offset']
    date_fmt = self._user['date_fmt'] if self._user['date_fmt'] else DEFAULT_DATE_FORMAT
    single['created_at_fmt'] = strftime(date_fmt.encode('UTF8'), localtime(t)).decode('UTF8')
    if 'source' in single:
      source = re.match(ur'<a .*>(.*)</a>', single['source'])
      single['source'] = source.group(1) if source else single['source']
    single['short_id_str_num'] = short_id
    single['short_id_str_alpha'] = short_id_alpha
    single['text'] = self.parse_text(single)
    if 'retweeted_status' in single:
      single['retweeted_status'] = self.make_namespace(single['retweeted_status'])
      retweet = single
      single = single['retweeted_status']
      single['retweet'] = retweet
      del single['retweet']['retweeted_status']
    if 'in_reply_to_status' in single:
      single['in_reply_to_status'] = self.make_namespace(single['in_reply_to_status'])
    self.allow_duplicate = old_allow_duplicate
    return single

  def parse_status(self, single):
    single = self.make_namespace(single, self.allow_duplicate)
    # TODO: implement cache
    # TODO: implement sandbox
    t = jinja2.Template(self._user['msg_tpl'] if self._user['msg_tpl'] else DEFAULT_MESSAGE_TEMPLATE)
    try:
      result = t.render(**single)
    except Exception, e:
      result = unicode(e)
    return result

  def parse_data(self, data, reverse=True):
    if data:
      msgs = list()
      if isinstance(data, list):
        if reverse:
          data.reverse()
        for single in data:
          try:
            text = self.parse_status(single)
            if text:
              msgs.append(text)
          except DuplicateError:
            pass
      else:
        try:
          text = self.parse_status(data)
          if text:
            msgs.append(text)
        except DuplicateError:
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
      short_id = alpha_to_digit(g)
    if short_id < MAX_ID_LIST_NUM:
      return db.get_long_id_from_short_id(self._user['id'], short_id)
    else:
      return short_id, db.TYPE_STATUS