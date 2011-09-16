import jinja2
from jinja2.sandbox import ImmutableSandboxedEnvironment

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


class Environment(ImmutableSandboxedEnvironment):
  def is_safe_callable(self, obj):
    return False

env = Environment(bytecode_cache=MemoryBytecodeCache(), cache_size=500)
env.globals = dict()

class Template(jinja2.Template):
  def __new__(cls, source):
    return env.from_string(source)