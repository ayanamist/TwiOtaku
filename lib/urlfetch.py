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


class Response(object):
  def __init__(self, status, data, headers):
    self.status = status
    self.data = data
    self.headers = headers


def fetch(url, method='GET', body=None, headers=None, block=True, timeout=None):
  req = urllib2.Request(url, data=body, headers=headers)
  # dirty hack for PUT DELETE method http://stackoverflow.com/questions/111945/is-there-any-way-to-do-http-put-in-python
  req.get_method = lambda: method
  if timeout is None:
    timeout = socket._GLOBAL_DEFAULT_TIMEOUT
  if block:
    code = httplib.OK
    try:
      r = urllib2.urlopen(req, timeout=timeout)
    except urllib2.HTTPError, e:
      code = e.code
      r = e
    except urllib2.URLError, e:
      raise Error(e.reason)
    return Response(code, r.read(), r.info())
  else:
    return urllib2.urlopen(req, timeout=timeout)

opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.CookieJar()), GZipHandler())
urllib2.install_opener(opener)