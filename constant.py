import os

ENVIRONMENT_JSON_PATH = '/home/dotcloud/environment.json'

YAML_PATH = os.path.dirname(__file__) + os.sep + 'dotcloud.yml'

DB_PATH = os.path.dirname(__file__) + os.sep + 'twiotaku.db'

CONFIG = dict()

CHARACTER_LIMIT = 140

REQUEST_TOKEN_URL = 'https://api.twitter.com/oauth/request_token'

ACCESS_TOKEN_URL = 'https://api.twitter.com/oauth/access_token'

AUTHORIZATION_URL = 'https://api.twitter.com/oauth/authorize'

SIGNIN_URL = 'https://api.twitter.com/oauth/authenticate'

BASE_URL = 'https://api.twitter.com/1'

  