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

import bisect

class URLUnwrapper(object):
    def __init__(self, s):
        self.original_s = s
        self._str_list = list()
        self._str_indices = [0]

    def __unicode__(self):
        if self._str_list:
            result = list()
            for i, s in enumerate(self._str_list):
                result.append(self.original_s[self._str_indices[i * 2]:self._str_indices[i * 2 + 1]])
                result.append(s)
            result.append(self.original_s[self._str_indices[-1]:])
            return u''.join(result)
        else:
            return unicode(self.original_s)

    def __str__(self):
        return unicode(self).encode('UTF8')

    def replace_indices(self, start, stop, replace_text):
        i = bisect.bisect(self._str_indices, start)
        self._str_indices.insert(i, start)
        self._str_indices.insert(i + 1, stop)
        self._str_list.insert(i // 2, replace_text)
        return self
  