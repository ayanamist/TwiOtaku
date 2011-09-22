import logging
import traceback
from functools import wraps
from StringIO import StringIO

from util import ThreadStop
# decorator for logging
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


def threadstop(f):
  def wrap(*args, **kwds):
    try:
      return f(*args, **kwds)
    except ThreadStop:
      return

  return wrap