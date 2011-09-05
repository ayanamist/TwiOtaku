import twitter
from config import OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET

def stream(queue, user):
  api = twitter.Api(consumer_key=OAUTH_CONSUMER_KEY,
                    consumer_secret=OAUTH_CONSUMER_SECRET,
                    access_token_key=user['access_key'],
                    access_token_secret=user['access_secret'])

  