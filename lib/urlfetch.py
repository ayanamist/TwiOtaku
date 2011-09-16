import httplib2
import logging

_h = httplib2.Http()
log = logging.getLogger('urlfetch')

class Response(httplib2.Response):
  def __init__(self, resp, content):
    super(Response, self).__init__(resp)
    self.data = content


def fetch(url, method='GET', body=None, headers=None):
  log.debug('Fetching %s' % url)
  resp, content = _h.request(uri=url, method=method, body=body, headers=headers)
  return Response(resp, content)
