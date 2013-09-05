# Copy this file into secrets.py and set keys, secrets and scopes.

# This is a session secret key used by webapp2 framework.
# Get 'a random and long string' from here: 
# http://clsc.net/tools/random-string-generator.php
# or execute this from a python shell: import os; os.urandom(64)
SESSION_KEY = "00ZEhaFOYJ42fUm0t8qL5S092Ed96ZAWrMMeau1C47Bls6P201"

# Google APIs
GOOGLE_APP_ID = 'gappyahoo'
GOOGLE_APP_SECRET = ''

# Facebook auth apis
FACEBOOK_APP_ID = 'app id'
FACEBOOK_APP_SECRET = 'app secret'

# Key/secret for both LinkedIn OAuth 1.0a and OAuth 2.0
# https://www.linkedin.com/secure/developer
LINKEDIN_KEY = 'consumer key'
LINKEDIN_SECRET = 'consumer secret'

# https://manage.dev.live.com/AddApplication.aspx
# https://manage.dev.live.com/Applications/Index
WL_CLIENT_ID = 'client id'
WL_CLIENT_SECRET = 'client secret'

# https://dev.twitter.com/apps
TWITTER_CONSUMER_KEY = 'oauth1.0a consumer key'
TWITTER_CONSUMER_SECRET = 'oauth1.0a consumer secret'

# https://foursquare.com/developers/apps
FOURSQUARE_CLIENT_ID = 'client id'
FOURSQUARE_CLIENT_SECRET = 'client secret'

# config that summarizes the above
AUTH_CONFIG = {
  # OAuth 2.0 providers
  'google'      : (GOOGLE_APP_ID, GOOGLE_APP_SECRET,
                  'https://www.googleapis.com/auth/userinfo.profile'),
  'linkedin2'   : (LINKEDIN_KEY, LINKEDIN_SECRET,
                  'r_basicprofile'),
  'facebook'    : (FACEBOOK_APP_ID, FACEBOOK_APP_SECRET,
                  'user_about_me'),
  'windows_live': (WL_CLIENT_ID, WL_CLIENT_SECRET,
                  'wl.signin'),
  'foursquare'  : (FOURSQUARE_CLIENT_ID,FOURSQUARE_CLIENT_SECRET,
                  'authorization_code'),

  # OAuth 1.0 providers don't have scopes
  'twitter'     : (TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET),
  'linkedin'    : (LINKEDIN_KEY, LINKEDIN_SECRET),

  # OpenID doesn't need any key/secret
}

# Membership
MONTHLY_MEMBERSHIP_FEE={'Nur':5.0,'Doc':20.0,'Client':5.0,'Super':100.0,'Trial':0.01}
TRIAL_DAYS=90


# Chat lease in minutes
CHAT_LEASE_IN_MINUTE=60

# Google wallet merchant
# Seller Identifier:	14174749540741466082
# Seller Secret:	TbGjq3UzUd4Mln6MIb3V9A
# POST back url: http://anthem-market-place.appspot.com/wallet/postback
GOOGLE_SELLER_ID='14174749540741466082' #production
#GOOGLE_SELLER_ID='14174749540741466082' #sandbox
#GOOGLE_SELLER_SECRET='GPrFWBaoNSEls-n2k0hsyw' # sandbox
GOOGLE_SELLER_SECRET='TbGjq3UzUd4Mln6MIb3V9A' # production

