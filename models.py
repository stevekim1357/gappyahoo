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
# Financial transaction models
#
#######################################
class AccountingSlip(MyBaseModel):
	# the cart this slip was created for
	cart_key=ndb.KeyProperty(kind='BuyOrderCart')
	
	# two parties of this transaction
	party_a=ndb.KeyProperty(kind='Contact')
	party_b=ndb.KeyProperty(kind='Contact')
	
	# who gives the amount to whom	
	money_flow=ndb.StringProperty(choices=['a-2-b','b-2-a'])
	
	# amount
	amount=ndb.FloatProperty()
	
	# since this is inherited from MyBaseModel
	# you get "audit_me" for free!
	# remember to save related information using
	# auditor so we essentially saving a state
	# when money changing hands

#######################################
#
# Business transaction models
#
#######################################
class BuyOrder(MyBaseModel):
	terminal_buyer=ndb.KeyProperty(kind='Contact') # optional
	name=ndb.StringProperty(required=True)
	description=ndb.TextProperty(default='')
	image=ndb.StringProperty(default='/static/img/default.png')
	qty=ndb.IntegerProperty(required=True)
	price=ndb.FloatProperty(required=True)
	payable=ndb.ComputedProperty(lambda self: self.qty*self.price)

	# tags is a string list tokenized self.name and self.description by white space
	# tags are all lower case!
	# TODO: use NLTK package to be intelligent
	tags=ndb.ComputedProperty(lambda self: tokenize(self.name), repeated=True)
	
	# category keywords
	# we are to be smart about this property so user doesn't need to input
	# instead, we will parse the tags and look for keywords that internally will map to a particular category
	# category keywords will function as tags when searching
	queues=ndb.ComputedProperty(lambda self: categorization(self.tags), repeated=True,indexed=True)
	
	# filled qty
	# order can only be deleted if filled_qty=0, meaning nobody has an expose to this record
	filled_qty=ndb.IntegerProperty(default=0)
	approved_qty=ndb.IntegerProperty(default=0)
	unfilled_qty=ndb.ComputedProperty(lambda self: self.qty-self.approved_qty)
	
	# closed
	# if set, this will not show on the browse page, and won't accept fills
	# however, existing fills are not affected
	is_closed=ndb.BooleanProperty(default=False)

	def can_delete(self):
		# buyorder can only be deleted if there is openning cart
		# meaning no user is exposed to this yet
		return self.filled_qty==0 and not self.is_closed

	def can_open(self):
		# buyorder can only be opened if is_closed=True
		return self.is_closed
			
	def can_close(self):
		# buyorder can be closed by its author
		# ongoing carts will continue in process
		# but this post will not be browsable anymore
		return self.is_closed==False
			
class BuyOrderFill(MyBaseModel):
	# buyoreder reference
	order=ndb.KeyProperty(kind='BuyOrder')
	
	# seller fill
	qty=ndb.IntegerProperty()
	price=ndb.FloatProperty()
	
	# computed payable
	payable=ndb.ComputedProperty(lambda self: self.qty*self.price)
	
	# broker fill
	client_price=ndb.FloatProperty()
	receivable=ndb.ComputedProperty(lambda self: self.client_price*self.qty)
	
	# accounting
	over_short=ndb.ComputedProperty(lambda self: self.receivable-self.payable)
	gross_margin=ndb.ComputedProperty(lambda self: self.over_short/self.payable*100.0 if self.payable else 0)

class BuyOrderCart(MyBaseModel):	
	terminal_seller=ndb.KeyProperty(kind='Contact')
	terminal_buyer=ndb.KeyProperty(kind='Contact')
	broker=ndb.KeyProperty(kind='Contact')

	# these flags should be MANUALLY set by each party of this transaction as an acknowledgement!
	buyer_reconciled=ndb.BooleanProperty(default=False)
	seller_reconciled=ndb.BooleanProperty(default=False)

	# overall status	
	status=ndb.StringProperty(choices=['Open',
		'In Approval',
		'Ready for Processing',
		'Rejected',
		'Closed',
		'In Shipment', 
		'Shipment In Dispute',
		'Shipment Clean',
		],default='Open')

	# shipping related
	shipping_status=ndb.StringProperty(choices=['Shipment Created','In Route','Delivery Confirmed','Destination Reconciled','In Dispute'],default='')
	shipping_carrier=ndb.StringProperty(choices=SHIPPING_METHOD)
	shipping_cost=ndb.FloatProperty(default=0)
	shipping_num_of_package=ndb.IntegerProperty(default=0)
	
	# allowing multiple tracking numbers
	shipping_tracking_number=ndb.StringProperty(default='')
	shipping_created_date=ndb.DateProperty() # when the info was entered  by user
	shipping_date=ndb.DateProperty() # actual shipping date by user
	shipping_label=ndb.BlobKeyProperty()
	
	# a cart has multiple fills
	fills=ndb.StructuredProperty(BuyOrderFill,repeated=True)
	
	# some status
	payable=ndb.ComputedProperty(lambda self: sum([f.payable for f in self.fills]))
	receivable=ndb.ComputedProperty(lambda self:sum([f.receivable for f in self.fills]))
	profit=ndb.ComputedProperty(lambda self: self.receivable-self.payable-self.shipping_cost)
	gross_margin=ndb.ComputedProperty(lambda self: self.profit/self.payable*100.0 if self.payable else 0)
			
	# a cart has multiple bank slips
	# broker, aka owner of these buyorders, is always "a"
	# payout: terminal seller is "b", slip is a-2-b, thus a cost to the broker
	# payin: termian client is "b", slip is b-2-a, thus an income to the broker
	payout_slips=ndb.KeyProperty(kind='AccountingSlip',repeated=True)
	payin_slips=ndb.KeyProperty(kind='AccountingSlip',repeated=True)
	payout=ndb.ComputedProperty(lambda self: sum([p.get().amount for p in self.payout_slips]))
	payin=ndb.ComputedProperty(lambda self: sum([p.get().amount for p in self.payin_slips]))
	payable_balance=ndb.ComputedProperty(lambda self: self.payable-self.payout)
	receivable_balance=ndb.ComputedProperty(lambda self: self.receivable-self.payin)
	
	# this is what we actually earned based on payin and payout
	realized_profit=ndb.ComputedProperty(lambda self: self.payin-self.payout)
	realized_gross_margin=ndb.ComputedProperty(lambda self: self.realized_profit/self.payout*100.0 if self.payout else 0)	

	# seller notes, whatever he needs to tell to buyer when submitting his cart
	seller_notes=ndb.StringProperty(default='')
	
	def can_view(self,user_key):
		# if usre is either a buyer, a seller or a broker
		# otherwise, they don't have the right to view this cart content!
		return self.terminal_seller==user_key or self.terminal_buyer==user_key or self.broker==user_key or user_key.get().nickname=='anthem.market.place'
	
	def can_enter_approval(self,user_key):
		# who can submit this cart for approval
		# it is determined the current cart status and current user
		return self.status in ['Open','Rejected'] and self.terminal_seller==user_key
		
	def can_approve(self,user_key):
		# who can approve a cart
		return self.status=='In Approval' and self.broker==user_key
		
	def can_change_fill(self,user_key):
		# based on cart status, shipping, and user_key
		# we determine whether fill info can be changed.
		# this includes qty, price and remove fill from cart
		
		# basically, fill can only be changed when the cart has not entered an agreement yet
		# also, only the cart owner can change
		return self.status in ['Open','Rejected'] and self.owner==user_key
	
	def can_change_shipping(self,user_key):
		# who can enter shipping information: label, packge, cost
		# shipping can be added when status=='Ready for Processing'
		# can only be changed when shipment has not been picked up yet: status='In Shipment' and shipping_status='Shipment Created'
		# also, only cart broker can start, this assumes that broker is to initiate shipping process by providing a label
		# 
		# once the shipment is "In Route", then nobody has access to this pane, and only certain field will be changed
		# depending on which state cart is in via individual command buttons on UI
		return (self.status=='Ready for Processing' or (self.status=='In Shipment' and self.shipping_status=='Shipment Created')) and self.broker==user_key
		
	def can_enter_shipping_in_route(self,user_key):
		# who actually ship the physical goods? this assumed to be the terminal_seller
		# In Route: item has been shipped (or picked by carrier) and is now in transition
		# if there is a tracking number, user can use it to track its logistics
		return self.status=='In Shipment' and self.shipping_status=='Shipment Created' and self.terminal_seller==user_key

	def can_confirm_shipping_delivery(self,user_key):
		# who actually confirm a delivery?
		# NOTE: this has to be different from who can enter_in_route!
		# so there is check & balance: one party ship, another party confirm
		# ideally, this should be the CARRIER, not the receiver, because of moral hazard!
		return self.status=='In Shipment' and self.shipping_status=='In Route' and self.broker==user_key

	def can_reconcile_destination(self,user_key):
		# delivery != satisfied
		# reconciling will indicate everything is as expected
		# eg. no broken package, no wrong items
		return self.shipping_status=='Delivery Confirmed' and self.broker==user_key
	
	def can_dispute_shipping(self,user_key):
		# who can put shipment in dispute?
		# ideally the receiver of packages
		# for now, assuming Doc
		# 
		# what to dispute?
		# 1. seller says it's shipped, but broker doesn't see it in tracking
		# 2. buyer confirmed delivery, but unsatisfied during reconciliation, like finding a broken packge
		return (self.shipping_status=='In Route'  and self.broker==user_key) or (self.shipping_status=='Delivery Confirmed' and self.broker==user_key)

	def can_seller_reconcile(self,user_key):
		# when payout>0, so seller get some kind of payment
		# this assumes that a cart can keep both broker and seller happy even
		# when its payable_balance>0
		return float(self.payout)>0 and not self.seller_reconciled and self.terminal_seller==user_key

	def can_delete_payout(self,user_key):
		# when can a user delete payout bankslip?
		# must before seller reconciliation, again, check and banalce
		# since the slip is registered by broker
		# so the only reconciliation threshold seller has is payable=payouts
		# thus, once seller says he is satisfied, broker can not change payout anymore!
		return self.status not in ['Closed','Open','Rejected'] and not self.seller_reconciled and self.broker==user_key
		
				
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
	
