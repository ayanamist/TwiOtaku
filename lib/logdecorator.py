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

import functools
import logging

def debug(f):
    @functools.wraps(f)
    def wrap(*args, **kwds):
        try:
            return f(*args, **kwds)
        except Exception, e:
            logging.exception(str(e))

    return wrap


def silent(f):
    @functools.wraps(f)
    def wrap(*args, **kwds):
        try:
            return f(*args, **kwds)
        except Exception:
            pass

    return wrap
