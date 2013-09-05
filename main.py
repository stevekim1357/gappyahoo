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
	Route('/admin/contact/reputation/link', handler='admin.AdminContactReputationLinkHandler', name='admin-contact-reputation-link'),
	Route('/admin/contact/reputation/score', handler='admin.AdminContactReputationScoreHandler', name='admin-contact-reputation-score'),
	Route('/admin/contact', handler='admin.AdminContactHandler', name='admin-contact'),
	Route('/admin/cart', handler='admin.AdminCartHandler', name='admin-cart'),
	
	# buyorder controllers
	Route('/blob/serve/<resource:[^/]+>/', handler='gappyahoo.ServeHandler',name='blobstore-serve'),
	Route('/buyorder/edit/<order_id:\d+>/', handler='gappyahoo.EditBuyOrder',name='buyorder-edit'),
	Route('/buyorder/delete/<order_id:\d+>/', handler='gappyahoo.DeleteBuyOrder',name='buyorder-delete'),
	Route('/buyorder/close/<order_id:\d+>/', handler='gappyahoo.CloseBuyOrder',name='buyorder-close'),
	Route('/buyorder/open/<order_id:\d+>/', handler='gappyahoo.OpenBuyOrder',name='buyorder-open'),
	Route('/buyorder/new', handler='gappyahoo.PublishNewBuyOrder', name='buyorder-new'),
	Route('/buyorder/browse/<order_id:\d+>/', handler='gappyahoo.BrowseBuyOrderById',name='buyorder-browse-id'),
	Route('/buyorder/browse', handler='gappyahoo.BrowseBuyOrder',name='buyorder-browse'),
	Route('/buyorder/owner/<owner_id:\d+>/<cat:[^/]+>/', handler='gappyahoo.BrowseBuyOrderByOwnerByCat',name='buyorder-browse-owner-cat'),  
	Route('/buyorder/owner/<owner_id:\d+>/', handler='gappyahoo.BrowseBuyOrderByOwner',name='buyorder-browse-owner'),  
	Route('/buyorder/manage', handler='gappyahoo.ManageBuyOrder',name='buyorder-manage'),  
	

	# user controllers
	Route('/user/contact/preference',handler='gappyahoo.ManageUserContactPreference',name='user-contact-preference'),	
	Route('/user/contact',handler='gappyahoo.ManageUserContact',name='user-contact'),	
	Route('/user/membership/cancel/<role:\w+>/',handler='gappyahoo.ManageUserMembershipCancel',name='user-membership-cancel'),	
	Route('/user/membership',handler='gappyahoo.ManageUserMembership',name='user-membership'),	
	Route('/user/riskprofile',handler='gappyahoo.ViewUserRiskProfile',name='user-risk-profile'),	
	
	
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
