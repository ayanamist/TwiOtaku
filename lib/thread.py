from threading import Thread, Event
from time import sleep
from functools import wraps

_sleep_interval_seconds = 1

class ThreadStop(BaseException):
  pass


class StoppableThread(Thread):
  _stop = Event()

  def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, verbose=None):
    Thread.__init__(self, group=group, target=target, name=name, args=args, kwargs=kwargs, verbose=verbose)
    self.setDaemon(True)

  def stop(self):
    self._stop.set()

  def is_stopped(self):
    return self._stop.is_set()

  def sleep(self, secs):
    i = 0
    while i < secs:
      self.check_stop()
      sleep(_sleep_interval_seconds)
      i += _sleep_interval_seconds

  def check_stop(self):
    if self.is_stopped():
      raise ThreadStop


def threadstop(f):
  @wraps(f)
  def wrap(*args, **kwds):
    try:
      return f(*args, **kwds)
    except ThreadStop:
      pass

  return wrap