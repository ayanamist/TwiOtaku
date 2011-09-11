from urllib3 import HTTPConnectionPool, HTTPSConnectionPool, get_host

_pool = dict()

def fetch(url, method='GET', body=None, headers=None, retries=3, redirect=True, assert_same_host=True):
  scheme, host, port = get_host(url)
  scheme = scheme.lower()
  host = host.lower()
  if scheme == 'https' and port == 443:
    port = None
  elif scheme == 'http' and port == 80:
    port = None
  hash_result = hash((scheme, host, port))
  pool = _pool.get(hash_result)
  if not pool:
    if scheme == 'https':
      pool = HTTPSConnectionPool(host, port=port)
    else:
      pool = HTTPConnectionPool(host, port=port)
    _pool[hash_result] = pool
  return pool.urlopen(url=url, method=method, body=body, headers=headers, retries=retries, redirect=redirect,
    assert_same_host=assert_same_host)
