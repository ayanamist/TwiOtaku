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

def digit_to_alpha(digit):
    if not isinstance(digit, int):
        raise TypeError('Only accept digit argument, but accept %s' % str(digit))
    nums = list()
    digit += 1
    while digit > 26:
        t = digit % 26
        if t > 0:
            nums.insert(0, t)
            digit //= 26
        else:
            nums.insert(0, 26)
            digit = digit // 26 - 1
    nums.insert(0, digit)
    return ''.join([chr(x + 64) for x in nums])


def alpha_to_digit(alpha):
    if not (isinstance(alpha, str) and alpha.isalpha()):
        raise TypeError('Only accept alpha argument, but accept %s.' % str(alpha))
    return reduce(lambda x, y: x * 26 + y, [ord(x) - 64 for x in alpha]) - 1
  