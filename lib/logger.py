import logging
import traceback
from functools import wraps
from StringIO import StringIO

def debug(f):
  @wraps(f)
  def wrap(*args, **kwds):
    try:
      return f(*args, **kwds)
    except Exception:
      err = StringIO()
      traceback.print_exc(file=err)
      logging.error(err.getvalue())

  return wrap

