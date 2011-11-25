try:
  from ujson import load, loads, dump, dumps
except ImportError:
  from json import load, loads, dump, dumps
  