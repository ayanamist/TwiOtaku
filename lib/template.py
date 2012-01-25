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

import jinja2
import jinja2.sandbox

_tpl_cache = dict()

class MemoryBytecodeCache(jinja2.BytecodeCache):
    def load_bytecode(self, bucket):
        if bucket.key in _tpl_cache:
            bucket.bytecode_from_string(_tpl_cache[bucket.key])

    def dump_bytecode(self, bucket):
        global _tpl_cache
        _tpl_cache[bucket.key] = bucket.bytecode_to_string()

    def clear(self):
        global _tpl_cache
        _tpl_cache = dict()


class Environment(jinja2.sandbox.ImmutableSandboxedEnvironment):
    def is_safe_callable(self, _):
        return False

env = Environment(bytecode_cache=MemoryBytecodeCache())
env.globals = dict()

class Template(jinja2.Template):
    def __new__(cls, source):
        return env.from_string(source)