# -*- coding: utf-8 -*-
import sys
from secrets import SESSION_KEY

from webapp2 import WSGIApplication, Route

# inject './lib' dir in the path so that we can simply do "import ndb" 
# or whatever there's in the app lib dir.
if 'lib' not in sys.path:
    sys.path[0:0] = ['lib']

# webapp2 config
app_config = {
  'webapp2_extras.sessions': {
    'cookie_name': '_simpleauth_sess',
    'secret_key': SESSION_KEY
  },
  'webapp2_extras.auth': {
    'user_attributes': []
  }
}
    
# Map URLs to handlers
routes = [
	Route('/profile', handler='handlers.ProfileHandler', name='profile'),
	Route('/logout', handler='handlers.AuthHandler:logout', name='logout'),
	Route('/auth/<provider>',handler='handlers.AuthHandler:_simple_auth', name='auth_login'),
	Route('/auth/<provider>/callback', handler='handlers.AuthHandler:_auth_callback', name='auth_callback'),

	# admin pages
	Route('/admin/contact', handler='admin.AdminContactHandler', name='admin-contact'),
	Route('/admin/newssource', handler='admin.AdminNewsSourceHandler', name='admin-news-source'),
	
	# controllers
	Route('/blob/serve/<resource:[^/]+>/', handler='gappyahoo.ServeHandler',name='blobstore-serve'),
	Route('/quote', handler='gappyahoo.YahooQuoteHandler', name='yahoo-quote'),
	Route('/news', handler='gappyahoo.NewsAnalysisHandler', name='news-analysis'),

	# user controllers
	Route('/user/contact/preference',handler='gappyahoo.ManageUserContactPreference',name='user-contact-preference'),	
	Route('/user/contact',handler='gappyahoo.ManageUserContact',name='user-contact'),	
	Route('/user/membership/cancel/<role:\w+>/',handler='gappyahoo.ManageUserMembershipCancel',name='user-membership-cancel'),	
	Route('/user/membership',handler='gappyahoo.ManageUserMembership',name='user-membership'),	
	
	
	# channel controller
	Route('/_ah/channel/connected/',handler='gappyahoo.ChannelConnected',name='channel-connected'),
	Route('/_ah/channel/disconnected/',handler='gappyahoo.ChannelDisconnected',name='channel-disconnected'),
	Route('/channel/token',handler='gappyahoo.ChannelToken',name='channel-token'),	
	Route('/channel/route',handler='gappyahoo.ChannelRouteMessage',name='channel-route-message'),	
	Route('/channel/list/onlineusers',handler='gappyahoo.ChannelListOnlineUsers',name='channel-list-onlineusers'),	

	# google wallet
	Route('/wallet/token',handler='gappyahoo.GoogleWalletToken',name='google-wallet-token'),	
	Route('/wallet/postback',handler='gappyahoo.GoogleWalletPostback',name='google-wallet-postback'),	
	Route('/wallet',handler='gappyahoo.GoogleWalletPostback',name='google-wallet-postback'),	
	
	# if everything falls out
	Route('/', handler='gappyahoo.MainPage'),  
	
]

app = WSGIApplication(routes, config=app_config, debug=False)
