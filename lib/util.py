# -*- encoding: utf-8 -*-
# Copyright 2011 ayanamist
# the program is distributed under the terms of the GNU General Public License
# This file is part of TwiOtaku.
#
#    Foobar is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    TwiOtaku is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with TwiOtaku.  If not, see <http://www.gnu.org/licenses/>.

import email.utils
import time

import config
import db
import twitter
from . import urlunwrapper
from . import template
from . import number

short_id_pattern = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

class DuplicateError(Exception):
    pass


class Util(object):
    allow_duplicate = True

    def __init__(self, user):
        self.__user = user
        self.__api = twitter.Api(consumer_key=config.OAUTH_CONSUMER_KEY, consumer_secret=config.OAUTH_CONSUMER_SECRET,
            access_token_key=self.__user['access_key'], access_token_secret=self.__user['access_secret'])

    def parse_text(self, data):
        def parse_entities(data):
            if 'entities' in data:
                tmp = urlunwrapper.URLUnwrapper(data['text'])

                urls = data['entities'].get('urls')
                if urls:
                    for url in urls:
                        tmp.replace_indices(url['indices'][0], url['indices'][1], url['expanded_url'])

                medias = data['entities'].get('media')
                if medias:
                    for media in medias:
                        tmp.replace_indices(media['indices'][0], media['indices'][1], media['media_url'])
                return unicode(tmp)
            else:
                return data['text']

        return parse_entities(data).replace('\r\n', '\n').replace('\r', '\n').replace("&lt;", "<")\
        .replace("&gt;", ">").replace("&amp;", "&")

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
        t = time.mktime(email.utils.parsedate(single['created_at']))
        t += 28800 # GMT+8
        date_fmt = self.__user['date_fmt'] if self.__user['date_fmt'] else config.DEFAULT_DATE_FORMAT
        single['created_at_fmt'] = time.strftime(date_fmt.encode('UTF8'), time.localtime(t)).decode('UTF8')
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
                    single['in_reply_to_status'] = self.__api.get_status(single['in_reply_to_status_id_str'])
                except twitter.Error:
                    pass
            single['in_reply_to_status'] = self.make_namespace(single['in_reply_to_status'])
        self.allow_duplicate = old_allow_duplicate
        return single

    def parse_status(self, single):
        single = self.make_namespace(single, self.allow_duplicate)
        if single:
            t = template.Template(self.__user['msg_tpl'] if self.__user['msg_tpl'] else config.DEFAULT_MESSAGE_TEMPLATE)
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
        short_id = db.get_short_id_from_long_id(self.__user['id'], long_id, single_type)
        if short_id is not None:
            if not self.allow_duplicate:
                raise DuplicateError
        else:
            self.__user['id_list_ptr'] += 1
            short_id = self.__user['id_list_ptr']
            if short_id >= config.MAX_ID_LIST_NUM:
                short_id = self.__user['id_list_ptr'] = 0
            db.update_user(id=self.__user['id'], id_list_ptr=short_id)
            db.update_long_id_from_short_id(self.__user['id'], short_id, long_id, single_type)
        return short_id, number.digit_to_alpha(short_id)

    def restore_short_id(self, short_id):
        short_id = str(short_id).upper()
        if short_id[0] == '#':
            g = short_id[1:]
        else:
            g = short_id
        if any(x not in short_id_pattern for x in g):
            raise TypeError('Incorrect short id %s.' % short_id)
        try:
            short_id = int(g)
        except ValueError:
            short_id = number.alpha_to_digit(g)
        if short_id < 0:
            raise ValueError('Unexpected value: %s' % str(short_id))
        if short_id < config.MAX_ID_LIST_NUM:
            return db.get_long_id_from_short_id(self.__user['id'], short_id)
        else:
            return short_id, db.TYPE_STATUS


