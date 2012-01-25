# Copyright 2011 ayanamist aka gh05tw01f
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

import threading
import time
import functools

__sleep_interval_seconds = 1

class ThreadStop(BaseException):
    pass


class StoppableThread(threading.Thread):
    _stop = threading.Event()

    def __init__(self, target=None, name=None, args=(), kwargs=None, verbose=None):
        super(StoppableThread, self).__init__(target=target, name=name, args=args, kwargs=kwargs, verbose=verbose)
        self.setDaemon(True)

    def stop(self):
        self._stop.set()

    def is_stopped(self):
        return self._stop.is_set()

    def sleep(self, secs):
        i = 0
        while i < secs:
            self.check_stop()
            time.sleep(__sleep_interval_seconds)
            i += __sleep_interval_seconds

    def check_stop(self):
        if self.is_stopped():
            raise ThreadStop


def monitorstop(f):
    @functools.wraps(f)
    def wrap(*args, **kwds):
        try:
            return f(*args, **kwds)
        except ThreadStop:
            pass

    return wrap