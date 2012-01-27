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

class Job(object):
    def __init__(self, jid, data=None, title=None, reverse=True, allow_duplicate=True, xmpp_command=True, always=True):
        self.data = data
        self.jid = jid
        self.title = title
        self.reverse = reverse
        self.allow_duplicate = allow_duplicate
        self.xmpp_command = xmpp_command
        self.always = always # always send message no matter client is online or not


