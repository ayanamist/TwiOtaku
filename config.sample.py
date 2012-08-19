# -*- encoding: utf-8 -*-
XMPP_USERNAME = 'username@gmail.com'
XMPP_PASSWORD = 'password'
OAUTH_CONSUMER_KEY = 'yourkey'
OAUTH_CONSUMER_SECRET = 'yoursecret'
MAX_ID_LIST_NUM = 702
MAX_CONVERSATION_NUM = 4
DATABASE_TYPE = 'sqlite' # only sqlite now.
DATABASE_DIR = '/home/dotcloud/data'
ADMIN_USERS = (
    'yourown1@domain.com',
    'yourown2@domail.com',
    )
DEFAULT_DATE_FORMAT = u'%m.%d %H:%M:%S'
DEFAULT_MESSAGE_TEMPLATE = u"""{% if user %}{{ user.screen_name }}{% else %}{{ sender_screen_name }}{% endif %}: {{ text }}
{{ created_at_fmt }} [{{ short_id_str_num }}={{ short_id_str_alpha }}]{% if source %} via {{ source }}{% endif %}{% if retweet %}
└Retweeted by {{ retweet.user.screen_name }} {{ retweet.created_at_fmt }} via {{ retweet.source }}{% endif %}{% if in_reply_to_status %}
┌────────────
{{ in_reply_to_status.user.screen_name }}: {{ in_reply_to_status.text }}
{{ in_reply_to_status.created_at_fmt }} via {{ in_reply_to_status.source }}
└────────────{% endif %}

"""
