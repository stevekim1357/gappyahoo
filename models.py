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
	
	# we don't need to know its residential
	shipping_address=ndb.StringProperty(indexed=False,default='')
	
	# shipping method preference
	# write whatever you want
	# eg. state, carrier, international
	shipping_preference=ndb.StringProperty(indexed=False,default='')
	
	# payment method preference
	# write whatever you want
	# eg. cash only, COD
	payment_preference=ndb.StringProperty(indexed=False,default='')
	
	# user reputation score
	# we shouldn't save comments here because this will burden datastore everytime we need
	# to validate Contact. Instead, we will retrieve comments and compute brand_equity score
	# when somebody views this user's comments.
	# user_comments=ndb.KeyProperty(kind='UserComment',repeated=True)
	
	# reputation score should not be computed!
	# thus allowing super user to manually set its value.
	# this is potentially needed to help user transit a status
	# from other site to ours
	reputation_score=ndb.IntegerProperty(default=100)
	reputation_link=ndb.StringProperty()
	
	# bank ending balance
	# this is how much money this user has on his account
	# payout will withdraw from this; payin will deposit to this
	# ending - beginning = sum(transactions)
	# so by getting sum of transactions and know this ending balance,
	# we can derive beginning balance also.
	cash=ndb.FloatProperty(default=0)

	def is_trial(self):
		# if it's in Trial period
		# Trial is limited to 30-day beginning at first creation of this Contact record
		# TODO: a CRON job to remove Trial from Contact based on 30-day age rule
		return 'Trial' in self.active_roles and self.trial_age<(TRIAL_DAYS*24*3600)

	def can_be_super(self):
		return self.nickname=='anthem.market.place'
				
	def can_be_doc(self):
		# if a Doc membership is Active
		return any([r in ['Doc','Super'] for r in self.active_roles]) or self.is_trial()

	def can_be_nur(self):
		# if a Nur membership is Active
		return any([r in ['Nur','Super'] for r in self.active_roles]) or self.is_trial()

	def can_be_client(self):
		# if a Client membership is Active
		return any([r in ['Client','Super'] for r in self.active_roles]) or self.is_trial()

	def get_eligible_memberships(self):
		available=[]
		if 'Nur' not in self.active_roles:
			available.append('Nur')
		if 'Doc' not in self.active_roles:
			available.append('Doc')
		return available
	
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
class Ticker(MyBaseModel):
	name=ndb.StringProperty()
	symbol=ndb.StringProperty()
	time_value=ndb.DateTimeProperty()
	money_value=ndb.FloatProperty()

				
#######################################
#
# Communication models
#
#######################################
class UserComment(MyBaseModel): 
	comment=ndb.StringProperty()
	rating=ndb.IntegerProperty() # 1-5


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
	
