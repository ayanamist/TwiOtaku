import urllib2
import httplib
import logging
import cookielib
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
  status = httplib.OK

  def __init__(self, fp):
    try:
      self.data = fp.read()
      self.headers = fp.info()
      self.final_url = fp.geturl()
    except urllib2.HTTPError, e:
      self.data = e.read()
      self.status = e.code
      self.headers = e.info()
      self.final_url = e.geturl()


def fetch(url, method='GET', body=None, headers=None):
  log.debug('Fetching %s' % url)
  req = urllib2.Request(url, data=body, headers=headers)
  # dirty hack for PUT DELETE method http://stackoverflow.com/questions/111945/is-there-any-way-to-do-http-put-in-python
  req.get_method = lambda: method
  try:
    r = urllib2.urlopen(req)
  except urllib2.URLError, e:
    raise Error(str(e))
  else:
    return Response(r)

opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.CookieJar()), GZipHandler())
urllib2.install_opener(opener)