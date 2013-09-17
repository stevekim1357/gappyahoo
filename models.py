from google.appengine.ext import ndb
from google.appengine.api.users import User
from google.appengine.api import mail
import datetime
from dateutil.relativedelta import relativedelta
from secrets import *
from myUtil import *

#######################################
#
# Dummy ancestor
#
#######################################
class DummyAncestor(ndb.Model):
	name=ndb.IntegerProperty(default=1)

#######################################
#
# Auditing models
#
#######################################
class MyAudit(ndb.Model):
	# when
	created_time=ndb.DateTimeProperty(auto_now_add=True)
	# by whome
	owner=ndb.KeyProperty(kind='Contact')
	# field name
	field_name=ndb.StringProperty(required=True)
	# old value
	old_value=ndb.GenericProperty()
	# new value
	new_value=ndb.GenericProperty()

#######################################
#
# User management models
#
#######################################
	
class Contact(ndb.Model):
	# key_name will be the user_id()
	email=ndb.StringProperty() # user email
	nickname=ndb.StringProperty() # user name
	communication=ndb.PickleProperty(default={'Phone':'','MITBBS':'','QQ':''}) # a dict

	# a Contact can sign up multiple membership kinds
	# each membership came from a GoogleWalletOrder so there is 1-1 relationship
	# between a membership and an order ID!
	memberships=ndb.KeyProperty(kind='GoogleWalletSubscriptionOrder',repeated=True)
	active_roles=ndb.ComputedProperty(lambda self: [m.get().role for m in self.memberships if m],repeated=True)
	is_active=ndb.ComputedProperty(lambda self: len(self.active_roles)>0)
	
	# Trial is a one-time deal
	trial_time=ndb.DateTimeProperty(default=datetime.datetime.now())
	trial_age=ndb.ComputedProperty(lambda self: (datetime.datetime.now()-self.trial_time).total_seconds())
	
	# bank ending balance
	# this is how much money this user has on his account
	# payout will withdraw from this; payin will deposit to this
	# ending - beginning = sum(transactions)
	# so by getting sum of transactions and know this ending balance,
	# we can derive beginning balance also.
	cash=ndb.FloatProperty(default=0)
	
	def signup_membership(self,g_order):
		# add auditing record
		my_audit=MyAudit(parent=self.key)
		my_audit.owner=self.key
		my_audit.field_name='Memberships'
		my_audit.old_value=','.join(self.active_roles)
		my_audit.new_value='Adding %s by order ID %s' % (g_order.role, g_order.order_id)
		my_audit.put_async() # async auditing
		
		self.memberships.append(g_order.key)
		if g_order.role=='Trial':
			self.trial_time=datetime.datetime.today()
		self.put()
		
		# remove Trial if new_membership !=Trial
		if g_order.role != 'Trial':
			self.cancel_membership('Trial')
	
	def cancel_membership(self,role):
		batch=[]
		
		# get canceling key
		being_canceled=[r for r in self.memberships if r.get().role==role]
		if len(being_canceled)==0: return # nothing to cancel
		
		# find candidate, go ahead
		order=being_canceled[0].get()
		order.cancel_date=datetime.datetime.today()
		batch.append(order)

		# setting up audit		
		my_audit=MyAudit(parent=self.key)
		my_audit.owner=self.key
		my_audit.field_name='Memberships'
		my_audit.old_value=','.join(self.active_roles)
		my_audit.new_value='Removing %s' % (role)
		my_audit.put_async() # async auditing

		# update contact
		self.memberships=[r for r in self.memberships if r.get().role !=role]
		batch.append(self)
		
		ndb.put_multi(batch)
		
		# notify ADMIN!
		message = mail.EmailMessage(sender="System <anthem.marketplace@gmail.com>",
                            subject="Subscription Cancelation")
		message.to='%s,%s'%('anthem.marketplace@gmail.com',self.email)
		message.body='User %s membership %s has been canceled.' % (self.nickname, role)
		message.send()		
				
	@classmethod
	def cancel_membership_by_wallet(order_id):
		# find order
		order=GoogleWalletSubscriptionOrder.query(ancestor=ndb.Key('DummyAncestor','WalletRoot')).filter(GoogleWalletSubscriptionOrder.order_id==order_id).get()
		assert order
	
		# update Contact
		order.contact_key.get().cancel_membership(order.role)
		

class GoogleWalletSubscriptionOrder(ndb.Model):
	# membership role
	role=ndb.StringProperty(required=True)
	
	# order id
	order_id=ndb.StringProperty(required=True)
	
	# JSON string from postback
	order_detail=ndb.TextProperty(required=True)
	
	# object key -- what was this order for?
	# eg. Contact, for membership
	contact_key=ndb.KeyProperty(kind='Contact')
	
	# user cancel
	cancel_date=ndb.DateProperty()
	is_canceled=ndb.ComputedProperty(lambda self: self.cancel_date!=None)
		
#######################################
#
# Abstract models
#
#######################################
class MyBaseModel(ndb.Model):
	# two time stamps
	created_time=ndb.DateTimeProperty(default=datetime.datetime.now())
	last_modified_time=ndb.DateTimeProperty(auto_now=True)
	
	# object owner tied to a Contact
	owner=ndb.KeyProperty(kind='Contact')
	last_modified_by=ndb.KeyProperty(kind='Contact')

	# age since inception, in seconds
	# http://docs.python.org/2/library/datetime.html#datetime.timedelta.total_seconds
	age=ndb.ComputedProperty(lambda self: (datetime.datetime.today()-self.created_time).total_seconds())

	def audit_me(self,contact_key,field_name,old_value,new_value):
		my_audit=MyAudit(parent=self.key)
		my_audit.owner=contact_key
		my_audit.field_name=field_name
		my_audit.old_value=old_value
		my_audit.new_value=new_value
		my_audit.put_async() # async auditing
		
#######################################
#
# Business models
#
#######################################
class RssSource(ndb.Model):
	name=ndb.StringProperty() # full name of the feed
	feed_url=ndb.StringProperty(required=True) # feed url
	etag=ndb.StringProperty() # etag, see http://pythonhosted.org/feedparser/http-etag.html
	root_link=ndb.StringProperty() # used to aggregate sub feeds from a same source
	provider=ndb.StringProperty() # user given idenntifiers, eg. Reuters, Bloomberg
	keywords=ndb.PickleProperty()
	
	
class NewsSource(ndb.Model):
	url=ndb.StringProperty(required=True)
	source=ndb.StringProperty(default='Other')
	css_selector=ndb.StringProperty()
	length_of_interest=ndb.IntegerProperty(default=50) # length of interest list
	link_depth=ndb.IntegerProperty(default=2) # follow links
	
class Ticker(MyBaseModel):
	name=ndb.StringProperty()
	symbol=ndb.StringProperty()
	time_value=ndb.DateTimeProperty()
	money_value=ndb.FloatProperty()

				
#######################################
#
# Channel models
#
#######################################
class ChatMessage(ndb.Model):
	created_time=ndb.DateTimeProperty(auto_now_add=True)
	sender_name=ndb.StringProperty(required=True)
	receiver_name=ndb.StringProperty(required=True)
	message=ndb.StringProperty(required=True)
	# age since inception, in seconds
	# this is a precaution if socket onClose does not fire, in which case
	# server will never know the channel has been closed on the client side
	# so we will sweep this record for any age > 2 hours and delete them
	# 2-hour is the default channel lease
	# on client side, once the lease is up, client has to refresh page to get
	# a new token instead of using the same channel token, thus setting age threshold
	# to 2-hour is sufficient 
	age=ndb.ComputedProperty(lambda self: (datetime.datetime.now()-self.created_time).total_seconds())
	is_expired=ndb.ComputedProperty(lambda self: int(self.age)>7200)

class ChatChannel(ndb.Model):
	created_time=ndb.DateTimeProperty(default=datetime.datetime.now())
	client_id=ndb.StringProperty(required=True)
	contact_id=ndb.StringProperty(required=True)
	contact_name=ndb.StringProperty(required=True)
	token=ndb.StringProperty(required=True)
	in_use=ndb.BooleanProperty(default=False)

	# age since inception, in seconds
	# http://docs.python.org/2/library/datetime.html#datetime.timedelta.total_seconds
	age=ndb.ComputedProperty(lambda self: (datetime.datetime.today()-self.created_time).total_seconds())
	
	# expiration: 2 hour inteval
	is_expired=ndb.ComputedProperty(lambda self: float(self.age)>7200)		
	
