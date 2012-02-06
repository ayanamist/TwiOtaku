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

import urllib2
import httplib
import logging
import cookielib
import socket
from StringIO import StringIO
from gzip import GzipFile

log = logging.getLogger('urlfetch')

class Error(Exception):
    pass


class GZipHandler(urllib2.BaseHandler):
    def http_response(self, _, resp):
        if resp.headers.get("content-encoding") == "gzip":
            gz = GzipFile(fileobj=StringIO(resp.read()), mode="r")
            old_resp = resp
            resp = urllib2.addinfourl(gz, old_resp.headers, old_resp.url, old_resp.code)
            resp.msg = old_resp.msg
        return resp

    https_response = http_response


def fetch_async(url, method='GET', body=None, headers=None, timeout=None):
    req = urllib2.Request(url, data=body, headers=headers)
    # dirty hack for PUT DELETE method http://stackoverflow.com/questions/111945/is-there-any-way-to-do-http-put-in-python
    req.get_method = lambda: method
    if timeout is None:
        timeout = socket._GLOBAL_DEFAULT_TIMEOUT
    code = httplib.OK
    try:
        r = urllib2.urlopen(req, timeout=timeout)
    except urllib2.HTTPError, e:
        code = e.code
        r = e
    except (urllib2.URLError, httplib.HTTPException), e:
        raise Error(str(e))
    r.status = code
    r.header = r.info()
    r.data = None
    return r


def fetch(url, method='GET', body=None, headers=None, timeout=None):
    r = fetch_async(url, method=method, body=body, headers=headers, timeout=timeout)
    r.data = r.read()
    return r

opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.CookieJar()), GZipHandler())
urllib2.install_opener(opener)