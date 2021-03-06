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

import httplib
import ssl
import urllib
import urlparse

import db
from . import oauth
from . import urlfetch
from . import myjson
from . import ttp


CHARACTER_LIMIT = 140

TCO_LENGTH = 20

REQUEST_TOKEN_URL = 'https://api.twitter.com/oauth/request_token'

ACCESS_TOKEN_URL = 'https://api.twitter.com/oauth/access_token'

AUTHORIZATION_URL = 'https://api.twitter.com/oauth/authorize'

SIGNIN_URL = 'https://api.twitter.com/oauth/authenticate'

BASE_URL = 'https://api.twitter.com/1.1'

_ttp_parser = ttp.Parser()

# twitter will convert all urls into t.co links.
def actual_len(text):
    length = len(text)
    parse_result = _ttp_parser.parse(text, html=False)
    for url in parse_result.urls:
        length = length - len(url) + TCO_LENGTH
    return length


class Error(Exception):
    def __str__(self):
        try:
            return "%d: %s" % (self.code, self.message)
        except AttributeError:
            return self.message


class BadRequestError(Error):
    code = 400


class UnauthorizedError(Error):
    code = 401


class ForbiddenError(Error):
    code = 403


class NotFoundError(Error):
    code = 404


class EnhanceYourCalmError(Error):
    code = 420


class InternalServerError(Error):
    code = 500


class BadGatewayError(Error):
    code = 502


class ServiceUnavailableError(Error):
    code = 503


class NetworkError(Error):
    code = 0


class DirectMessage(dict):
    pass


class Api(object):
    def __init__(self, consumer_key=None, consumer_secret=None, access_token_key=None, access_token_secret=None,
                 input_encoding=None, request_headers=None, base_url=None):
        self._input_encoding = input_encoding
        self._oauth_consumer = None
        self._initialize_request_headers(request_headers)
        if base_url is None:
            self.base_url = BASE_URL
        else:
            self.base_url = base_url
        self.set_credentials(consumer_key, consumer_secret, access_token_key, access_token_secret)

    def set_credentials(self, consumer_key, consumer_secret, access_token_key=None, access_token_secret=None):
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret
        self._access_token_key = access_token_key
        self._access_token_secret = access_token_secret
        self._oauth_consumer = None
        if consumer_key is not None and consumer_secret is not None\
           and access_token_key is not None and access_token_secret is not None:
            self._signature_method_hmac_sha1 = oauth.SignatureMethod_HMAC_SHA1()
            self._oauth_token = oauth.Token(key=access_token_key, secret=access_token_secret)
            self._oauth_consumer = oauth.Consumer(key=consumer_key, secret=consumer_secret)

    def clear_credentials(self):
        self._consumer_key = None
        self._consumer_secret = None
        self._access_token_key = None
        self._access_token_secret = None
        self._oauth_consumer = None

    def get_home_timeline(self, page=1, since_id=None, include_rts=True, include_entities=True):
        parameters = {'page': int(page), 'include_rts': int(bool(include_rts)),
                      'include_entities': int(bool(include_entities))}
        if since_id:
            parameters['since_id'] = since_id
        url = '%s/statuses/home_timeline.json' % self.base_url
        return self._fetch_url(url, parameters=parameters)

    def get_user_timeline(self, user_id=None, screen_name=None, since_id=None, max_id=None, count=None,
                          page=None, include_rts=True, include_entities=True):
        parameters = {'include_rts': int(bool(include_rts)), 'include_entities': int(bool(include_entities))}
        url = '%s/statuses/user_timeline.json' % self.base_url
        if user_id:
            parameters['user_id'] = user_id
        elif screen_name:
            parameters['screen_name'] = screen_name
        if since_id:
            parameters['since_id'] = since_id
        if max_id:
            parameters['max_id'] = max_id
        if count:
            parameters['count'] = int(count)
        if page:
            parameters['page'] = int(page)
        return self._fetch_url(url, parameters=parameters)

    def get_related_results(self, id, include_entities=True):
        #related_result api is only available in api version 1
        url = '%s/related_results/show/%s.json' % ('https://api.twitter.com/1', str(id))
        parameters = {'include_entities': int(bool(include_entities))}
        return self._fetch_url(url, parameters=parameters)

    def get_status(self, id, include_entities=True):
        cache = db.get_cache(id)
        if not cache:
            url = '%s/statuses/show/%s.json' % (self.base_url, str(id))
            parameters = {'include_entities': int(bool(include_entities))}
            return self._fetch_url(url, parameters=parameters)
        else:
            return cache

    def destroy_status(self, id, include_entities=True):
        parameters = {'include_entities': int(bool(include_entities))}
        url = '%s/statuses/destroy/%s.json' % (self.base_url, str(id))
        return self._fetch_url(url, post_data={'id': str(id)}, parameters=parameters)

    def post_update(self, status, in_reply_to_status_id=None, include_entities=True):
        url = '%s/statuses/update.json' % self.base_url
        data = {'status': status, 'include_entities': int(bool(include_entities))}
        if in_reply_to_status_id:
            data['in_reply_to_status_id'] = in_reply_to_status_id
        return self._fetch_url(url, post_data=data)

    def get_user(self, screen_name, include_entities=True):
        url = '%s/users/show.json' % self.base_url
        parameters = {'screen_name': screen_name, 'include_entities': int(bool(include_entities))}
        return self._fetch_url(url, parameters=parameters)

    def get_direct_messages(self, since_id=None, page=None, include_entities=True, max_id=None, count=None):
        url = '%s/direct_messages.json' % self.base_url
        parameters = {'include_entities': int(bool(include_entities))}
        if since_id:
            parameters['since_id'] = since_id
        if page:
            parameters['page'] = int(page)
        if max_id:
            parameters['max_id'] = max_id
        if count:
            parameters['count'] = int(count)
        return [DirectMessage(x) for x in self._fetch_url(url, parameters=parameters)]

    def get_sent_direct_messages(self, since_id=None, page=None, include_entities=True, max_id=None, count=None):
        url = '%s/direct_messages/sent.json' % self.base_url
        parameters = {'include_entities': int(bool(include_entities))}
        if since_id:
            parameters['since_id'] = since_id
        if page:
            parameters['page'] = int(page)
        if max_id:
            parameters['max_id'] = max_id
        if count:
            parameters['count'] = int(count)
        return [DirectMessage(x) for x in self._fetch_url(url, parameters=parameters)]

    def get_direct_message(self, id, include_entities=True):
        data = self.get_direct_messages(max_id=id, count=1, include_entities=int(bool(include_entities)))
        if data and data[0]['id_str'] == str(id):
            return data[0]
        else:
            raise NotFoundError

    def post_direct_message(self, user, text, include_entities=True):
        url = '%s/direct_messages/new.json' % self.base_url
        data = {'text': text, 'user': user, 'include_entities': int(bool(include_entities))}
        return DirectMessage(self._fetch_url(url, post_data=data))

    def destroy_direct_message(self, id, include_entities=True):
        url = '%s/direct_messages/destroy/%s.json' % (self.base_url, str(id))
        data = {'id': id, 'include_entities': int(bool(include_entities))}
        return DirectMessage(self._fetch_url(url, post_data=data))

    def create_friendship(self, user):
        url = '%s/friendships/create.json' % self.base_url
        return self._fetch_url(url, parameters={'screen_name': user}, http_method='POST')

    def destroy_friendship(self, user):
        url = '%s/friendships/destroy.json' % self.base_url
        return self._fetch_url(url, parameters={'screen_name': user}, http_method='POST')

    def show_friendship(self, source_screen_name, target_screen_name):
        url = '%s/friendships/show.json' % self.base_url
        return self._fetch_url(url, parameters={'source_screen_name': source_screen_name, 'target_screen_name': target_screen_name})

    def create_favorite(self, id):
        url = '%s/favorites/create.json' % self.base_url
        return self._fetch_url(url, post_data={'id': id})

    def destroy_favorite(self, id):
        url = '%s/favorites/destroy.json' % self.base_url
        return self._fetch_url(url, post_data={'id': id})

    def get_favorites(self, screen_name=None, page=None, include_entities=True):
        url = '%s/favorites/list.json' % self.base_url
        parameters = {'include_entities': int(bool(include_entities))}
        if page:
            parameters['page'] = int(page)
        if screen_name:
            parameters['id'] = screen_name
        return self._fetch_url(url, parameters=parameters)

    def get_mentions(self, since_id=None, max_id=None, page=None, include_entities=True):
        url = '%s/statuses/mentions_timeline.json' % self.base_url
        parameters = {'include_entities': int(bool(include_entities))}
        if since_id:
            parameters['since_id'] = since_id
        if max_id:
            parameters['max_id'] = max_id
        if page:
            parameters['page'] = int(page)
        return self._fetch_url(url, parameters=parameters)

    def create_retweet(self, id):
        url = '%s/statuses/retweet/%s.json' % (self.base_url, id)
        return self._fetch_url(url, http_method='POST')

    def create_list(self, name, public=True):
        url = '%s/lists/create.json' % self.base_url
        parameters = {'name': name}
        if not public:
            parameters['mode'] = 'private'
        return self._fetch_url(url, parameters=parameters, http_method='POST')

    def destroy_list(self, owner_screen_name, slug):
        url = '%s/lists/destroy.json' % self.base_url
        parameters = {'owner_screen_name': owner_screen_name, 'slug': slug}
        return self._fetch_url(url, parameters=parameters, http_method='POST')

    def create_list_member(self, owner_screen_name, slug, screen_name):
        url = '%s/lists/members/create.json' % self.base_url
        parameters = {'owner_screen_name': owner_screen_name, 'slug': slug, 'screen_name': screen_name}
        return self._fetch_url(url, parameters=parameters, http_method='POST')

    def destroy_list_member(self, owner_screen_name, slug, screen_name):
        url = '%s/lists/members/destroy.json' % self.base_url
        parameters = {'owner_screen_name': owner_screen_name, 'slug': slug, 'screen_name': screen_name}
        return self._fetch_url(url, parameters=parameters, http_method='POST')

    def get_all_lists(self, screen_name=None):
        url = '%s/lists/list.json' % self.base_url
        parameters = dict()
        if screen_name:
            parameters['screen_name'] = screen_name
        return self._fetch_url(url, parameters=parameters)

    def get_list(self, screen_name, slug):
        url = '%s/lists/show.json' % self.base_url
        parameters = {'slug': slug, 'owner_screen_name': screen_name}
        return self._fetch_url(url, parameters=parameters)

    def get_list_statuses(self, screen_name, slug, since_id=None, max_id=None, page=None, include_entities=True,
                          include_rts=True):
        url = '%s/lists/statuses.json' % self.base_url
        parameters = {'slug': slug, 'owner_screen_name': screen_name, 'include_entities': int(bool(include_entities)),
                      'include_rts': int(bool(include_rts))}
        if since_id:
            parameters['since_id'] = since_id
        if max_id:
            parameters['max_id'] = max_id
        if page:
            parameters['page'] = int(page)
        return self._fetch_url(url, parameters=parameters)

    def get_list_members(self, screen_name, slug, cursor=-1, skip_status=False, include_entities=False):
        url = '%s/lists/members.json' % self.base_url
        parameters = {'slug': slug, 'owner_screen_name': screen_name, 'cursor': int(cursor)}
        if skip_status:
            parameters['skip_status'] = 1
        if include_entities:
            parameters['include_entities'] = 1
        return self._fetch_url(url, parameters=parameters)

    def create_block(self, screen_name):
        url = '%s/blocks/create.json' % self.base_url
        return self._fetch_url(url, parameters={'screen_name': screen_name}, http_method='POST')

    def report_spam(self, screen_name):
        url = '%s/report_spam.json' % self.base_url
        return self._fetch_url(url, parameters={'screen_name': screen_name}, http_method='POST')

    def destroy_block(self, screen_name):
        url = '%s/blocks/destroy.json' % self.base_url
        return self._fetch_url(url, parameters={'screen_name': screen_name}, http_method='POST')

    def get_blocking_ids(self, stringify_ids=False):
        parameters = {'stringify_ids': int(bool(stringify_ids))}
        url = '%s/blocks/ids.json' % self.base_url
        return self._fetch_url(url, parameters=parameters)

    def verify_credentials(self):
        url = '%s/account/verify_credentials.json' % self.base_url
        return self._fetch_url(url)

    def get_search(self, q, page=None, since_id=None, rpp=None, count=None, include_entities=True):
        url = 'http://search.twitter.com/search.json'
        parameters = {'q': q}
        if page:
            parameters['page'] = int(page)
        if since_id:
            parameters['since_id'] = since_id
        if rpp:
            parameters['rpp'] = int(rpp)
        if count:
            parameters['count'] = int(count)
        if include_entities:
            parameters['include_entities'] = True
        return self._fetch_url(url, parameters=parameters)

    def _build_url(self, url, path_elements=None, extra_params=None):
        (scheme, netloc, path, params, query, fragment) = urlparse.urlparse(url)
        if path_elements:
            p = [i for i in path_elements if i]
            if not path.endswith('/'):
                path += '/'
            path += '/'.join(p)
        if extra_params and len(extra_params) > 0:
            extra_query = self._encode_parameters(extra_params)
            if query:
                query += '&' + extra_query
            else:
                query = extra_query
        return urlparse.urlunparse((scheme, netloc, path, params, query, fragment))

    def _initialize_request_headers(self, request_headers):
        if request_headers:
            self._request_headers = request_headers
        else:
            self._request_headers = {}

    def _encode(self, s):
        if self._input_encoding:
            return unicode(s, self._input_encoding).encode('utf-8')
        else:
            return unicode(s).encode('utf-8')

    def _encode_parameters(self, parameters):
        return urllib.urlencode(dict([(k, self._encode(v)) for k, v in parameters.items() if v is not None]))

    def _encode_post_data(self, post_data):
        if post_data is None:
            return None
        else:
            return urllib.urlencode(dict([(k, self._encode(v)) for k, v in post_data.items()]))

    def _get_twitter_data_error(self, response):
        if response.data is not None:
            try:
                data = myjson.loads(response.data)
            except ValueError:
                pass
            else:
                response.data = data
                if isinstance(data, dict) and 'error' in data:
                    return data['error']
        return ''

    def _check_for_twitter_code_error(self, response, error_message=''):
        if response.status == httplib.OK:
            pass
        elif response.status == httplib.BAD_REQUEST:
            raise BadRequestError(error_message)
        elif response.status == httplib.UNAUTHORIZED:
            raise UnauthorizedError(error_message)
        elif response.status == httplib.FORBIDDEN:
            raise ForbiddenError(error_message)
        elif response.status == httplib.NOT_FOUND:
            raise NotFoundError(error_message)
        elif response.status == 420:
            raise EnhanceYourCalmError(error_message)
        elif response.status == httplib.INTERNAL_SERVER_ERROR:
            raise InternalServerError(error_message)
        elif response.status == httplib.BAD_GATEWAY:
            raise BadGatewayError(error_message)
        elif response.status == httplib.SERVICE_UNAVAILABLE:
            raise ServiceUnavailableError(error_message)
        else:
            raise Error('%d: %s' % (response.status, str(error_message)))

    def _fetch_url_async(self, url, post_data=None, parameters=None, http_method='GET', timeout=None):
        headers = {'Accept-Encoding': 'gzip'}
        extra_params = dict()
        if parameters is not None:
            extra_params.update(parameters)
        if post_data:
            http_method = "POST"
            # it seems that adding following header will increase call-limit from 350 to 1000.
        if http_method == 'GET':
            headers['X-PHX'] = 'true'
        if self._oauth_consumer is not None:
            if post_data:
                parameters = post_data.copy()
            req = oauth.Request.from_consumer_and_token(self._oauth_consumer, token=self._oauth_token,
                http_method=http_method, http_url=url,
                parameters=parameters)
            req.sign_request(self._signature_method_hmac_sha1, self._oauth_consumer, self._oauth_token)
            if http_method == "POST":
                encoded_post_data = req.to_postdata()
            else:
                encoded_post_data = None
                url = req.to_url()
        else:
            url = self._build_url(url, extra_params=extra_params)
            encoded_post_data = self._encode_post_data(post_data)
        try:
            response = urlfetch.fetch_async(method=http_method, url=url, body=encoded_post_data, headers=headers,
                timeout=timeout)
        except (ssl.SSLError, urlfetch.Error), e:
            raise NetworkError(str(e))
        return response

    def _fetch_url(self, url, post_data=None, parameters=None, http_method='GET'):
        r = self._fetch_url_async(url, post_data=post_data, parameters=parameters, http_method=http_method)
        try:
            r.data = r.read()
        except IOError, e:
            raise Error(str(e))
        else:
            self._check_for_twitter_code_error(r, self._get_twitter_data_error(r))
            return r.data

    def user_stream(self, timeout, reply_all=True, track=None):
        url = 'https://userstream.twitter.com/2/user.json'
        parameters = dict(delimited='length')
        if reply_all:
            parameters['replies'] = 'all'
        if track:
            parameters['track'] = ','.join(track) if isinstance(track, list) else track
        response = self._fetch_url_async(url=url, parameters=parameters, timeout=timeout)
        self._check_for_twitter_code_error(response)
        return response
