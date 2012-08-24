# Copyright 2011 ayanamist
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

import config

MODE_NONE = 0
MODE_DM = 1
MODE_MENTION = 2
MODE_HOME = 4
MODE_LIST = 8
MODE_EVENT = 16
MODE_TRACK = 32

TYPE_STATUS = 0
TYPE_DM = 1

dbapi = __import__(config.DATABASE_TYPE.lower(), globals=globals(), locals=locals())

g = globals()
for x in dir(dbapi):
    g[x] = getattr(dbapi, x)
