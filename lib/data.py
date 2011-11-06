# -*- encoding: utf-8 -*-
from operator import itemgetter
from itertools import ifilter, imap
from bisect import bisect
from array import array
from time import mktime, localtime, strftime
from email.utils import parsedate

import db
import twitter
from template import Template
from number import alpha_to_digit, digit_to_alpha
from config import MAX_ID_LIST_NUM, DEFAULT_MESSAGE_TEMPLATE, DEFAULT_DATE_FORMAT, OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET

short_id_pattern = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

class DuplicateError(Exception):
  pass


class ostring(object):
  def __init__(self, s):
    self.original_s = s
    self._str_list = list()
    self._str_indices = array('H', [0])

  def __unicode__(self):
    if self._str_list:
      result = list()
      for i, s in enumerate(self._str_list):
        result.append(self.original_s[self._str_indices[i * 2]:self._str_indices[i * 2 + 1]])
        result.append(s)
      result.append(self.original_s[self._str_indices[-1]:])
      return u''.join(result)
    else:
      return unicode(self.original_s)

  def __str__(self):
    return unicode(self).encode('UTF8')

  def replace_indices(self, start, stop, replace_text):
    i = bisect(self._str_indices, start)
    self._str_indices.insert(i, start)
    self._str_indices.insert(i + 1, stop)
    self._str_list.insert(i // 2, replace_text)
    return self


class Util(object):
  allow_duplicate = True

  def __init__(self, user):
    self._user = user
    self._api = twitter.Api(consumer_key=OAUTH_CONSUMER_KEY, consumer_secret=OAUTH_CONSUMER_SECRET,
      access_token_key=self._user['access_key'], access_token_secret=self._user['access_secret'])

  def parse_text(self, data):
    def parse_entities(data):
      if 'entities' in data:
        tmp = ostring(data['text'])
        for url in ifilter(itemgetter('expanded_url'), data['entities'].get('urls', tuple())):
          tmp.replace_indices(url['indices'][0], url['indices'][1], url['expanded_url'])
        for media in ifilter(itemgetter('media_url'), data['entities'].get('media', tuple())):
          tmp.replace_indices(media['indices'][0], media['indices'][1], media['media_url'])
        return unicode(tmp)
      else:
        return data['text']

    return parse_entities(data).replace('\r\n', '\n').replace('\r', '\n').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

  def make_namespace(self, single, allow_duplicate=True):
    if single is None:
      return None
    old_allow_duplicate = self.allow_duplicate
    self.allow_duplicate = allow_duplicate
    if isinstance(single, twitter.DirectMessage):
      single_type = db.TYPE_DM
    else:
      single_type = db.TYPE_STATUS
    short_id, short_id_alpha = self.generate_short_id(single['id_str'], single_type)
    t = mktime(parsedate(single['created_at']))
    t += 28800 # GMT+8
    date_fmt = self._user['date_fmt'] if self._user['date_fmt'] else DEFAULT_DATE_FORMAT
    single['created_at_fmt'] = strftime(date_fmt.encode('UTF8'), localtime(t)).decode('UTF8')
    single_source = single.get('source')
    if single_source:
      gt_index = single_source.find('>')
      lt_index = single_source.rfind('<')
      if gt_index != -1 and lt_index != -1:
        single['source'] = single_source[gt_index + 1:lt_index]
    single['short_id_str_num'] = short_id
    single['short_id_str_alpha'] = short_id_alpha
    single['text'] = self.parse_text(single)
    retweeted_status = single.get('retweeted_status')
    if retweeted_status:
      single['retweeted_status'] = self.make_namespace(retweeted_status)
      retweet = single
      single = retweeted_status
      single['retweet'] = retweet
      del single['retweet']['retweeted_status']
    if 'in_reply_to_status' in single:
      if not single['in_reply_to_status']:
        try:
          single['in_reply_to_status'] = self._api.get_status(single['in_reply_to_status_id_str'])
        except BaseException:
          pass
      single['in_reply_to_status'] = self.make_namespace(single['in_reply_to_status'])
    self.allow_duplicate = old_allow_duplicate
    return single

  def parse_status(self, single):
    single = self.make_namespace(single, self.allow_duplicate)
    if single:
      t = Template(self._user['msg_tpl'] if self._user['msg_tpl'] else DEFAULT_MESSAGE_TEMPLATE)
      try:
        result = t.render(**single)
      except Exception, e:
        result = unicode(e)
    else:
      result = ''
    return result

  def parse_data(self, data, reverse=True):
    msgs = list()
    if isinstance(data, list):
      if reverse:
        data = reversed(data)
      for single in data:
        try:
          text = self.parse_status(single)
          if text:
            msgs.append(text)
        except DuplicateError:
          pass
    elif isinstance(data, dict):
      try:
        text = self.parse_status(data)
        if text:
          msgs.append(text)
      except DuplicateError:
        pass
    else:
      raise TypeError('Unknown data type: %s' % str(data))
    return msgs


  def generate_short_id(self, long_id, single_type):
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
    short_id = str(short_id).upper()
    if short_id[0] == '#':
      g = short_id[1:]
    else:
      g = short_id
    if any(imap(lambda x: x not in short_id_pattern, g)):
      raise TypeError('Incorrect short id %s.' % short_id)
    try:
      short_id = int(g)
    except ValueError:
      short_id = alpha_to_digit(g)
    if short_id < 0:
      raise ValueError('Unexpected value: %s' % str(short_id))
    if short_id < MAX_ID_LIST_NUM:
      return db.get_long_id_from_short_id(self._user['id'], short_id)
    else:
      return short_id, db.TYPE_STATUS


