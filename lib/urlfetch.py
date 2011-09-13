import httplib2

_h = httplib2.Http()

class Response(httplib2.Response):
  def __init__(self, resp, content):
    super(Response, self).__init__(resp)
    self.data = content


def fetch(url, method='GET', body=None, headers=None):
  resp, content = _h.request(uri=url, method=method, body=body, headers=headers)
  return Response(resp, content)
