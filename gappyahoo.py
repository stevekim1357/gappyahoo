import webapp2
from google.appengine.api import users
from google.appengine.ext import blobstore
from google.appengine.api import images
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext.blobstore import delete, delete_async
from google.appengine.api import channel
from webapp2 import uri_for,redirect
import os
import urllib
import json
import cgi
import logging
import datetime
import time
import jwt # google wallet token
import jinja2
from models import *
from myUtil import *
from secrets import *

JINJA_ENVIRONMENT = jinja2.Environment(
	loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
	extensions=['jinja2.ext.autoescape'])


####################################################
#
# Static Page Controllers
#
####################################################

class MainPage(webapp2.RequestHandler):
	def get(self):
		#self.redirect('/buyorder/browse')
		template = JINJA_ENVIRONMENT.get_template('/template/Home.html')
		self.response.write(template.render())

		
####################################################
#
# Base Controllers
#
####################################################

class ServeHandler(blobstore_handlers.BlobstoreDownloadHandler):
	def get(self, resource):
		# resource is actually a blobkey
  		resource = str(urllib.unquote(resource))
  		blob_info = blobstore.BlobInfo.get(resource)
  		self.send_blob(blob_info)
                      
class ComplexEncoder(json.JSONEncoder):
	def default(self, obj):
		if isinstance(obj, datetime.date):
			epoch = datetime.datetime.utcfromtimestamp(0)
			delta = obj - epoch
			return delta.total_seconds()
			#return obj.isoformat()
		elif isinstance(obj,datetime.datetime):
			epoch = datetime.datetime.utcfromtimestamp(0)
			delta = obj - epoch
			return delta.total_seconds()
		elif isinstance(obj,users.User):
			return {'email':obj.email(),'id':obj.user_id(),'nickname':obj.nickname()}
		elif isinstance(obj,ndb.Key):
			if obj.kind()=='Contact':
				contact=obj.get()
				return {'name':contact.nickname,'email':contact.email,'id':contact.key.id()}
			elif obj.kind()=='BuyOrder':
				o=obj.get()
				return {'name':o.name,'description':o.description,'id':o.key.id(),'owner':o.owner}
		else:
			return json.JSONEncoder.default(self, obj)

class MyBaseHandler(webapp2.RequestHandler):
	def __init__(self, request=None, response=None):
		webapp2.RequestHandler.__init__(self,request,response) # extend the base class
		self.template_values={}		
		self.template_values['user']=self.user = users.get_current_user()
		self.template_values['me']=self.me=self.get_contact()
		self.template_values['cart']=self.cart=self.get_open_cart()
		self.template_values['url_login']=users.create_login_url(self.request.url)
		self.template_values['url_logout']=users.create_logout_url('/')
		
	def get_contact(self):
		# manage contact -- who is using my service?
		# update email and user name
		# this is to keep Google user account in sync with internal Contact model
		user = self.user
		me=Contact.get_or_insert(ndb.Key('Contact',user.user_id()).string_id(),
			email=user.email(),
			nickname=user.nickname(),
			cash=0)
			
		# initiate membership with a Trial if contact has none
		if len(me.memberships)==0:
			fake_order=GoogleWalletSubscriptionOrder(role='Trial',
				order_id='000000',
				order_detail='',
				contact_key=me.key)
			fake_order.put()
			me.signup_membership(fake_order)
		return me

	def get_open_cart(self):
		# get open cart where terminal_seller == current login user
		# if BuyOrder was creatd with a particular termianl_buyer specified
		# we need to locate the cart that has the matching (terminal_buyer,terminal_seller) pair
		# 
		# RULE -- single OPEN cart per terminal_seller rule
		# open_cart=BuyOrderCart.query(BuyOrderCart.terminal_seller==me.key,BuyOrderCart.status=='Open')
		open_cart=BuyOrderCart.query(ancestor=self.me.key).filter(BuyOrderCart.status=='Open')
		assert open_cart.count()<2
		if open_cart.count():
			my_cart=open_cart.get() # if there is one
		else:
			# if no such cart, create one
			# we are making this cart and Contact an entity group
			# this will enforce data consistency
			my_cart=BuyOrderCart(terminal_seller=self.me.key,status='Open',parent=self.me.key)
			my_cart.owner=self.me.key
			my_cart.last_modified_by=self.me.key
			my_cart.shipping_cost=0
			my_cart.put()
		return my_cart

####################################################
#
# BuyOrder Controllers
#
####################################################

class EditBuyOrder(MyBaseHandler):
	def get(self, order_id):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		

		order=BuyOrder.get_by_id(int(order_id))
		assert order
		
		# only owner of this order or super can edit
		if order.owner==self.me.key or self.me.can_be_super():
			self.template_values['order']=order
		else:
			return self.response.write('You do not have the right to edit this order.')
				
		template = JINJA_ENVIRONMENT.get_template('/template/PublishNewBuyOrder.html')
		self.response.write(template.render(self.template_values))

class DeleteBuyOrder(MyBaseHandler):
	def post(self, order_id):
		order=BuyOrder.get_by_id(int(order_id))
		assert order
		
		# only owner of this order or super can edit
		if order.owner==self.me.key or self.me.can_be_super():
			if order.filled_qty:
				return self.response.write('There are open shopping orders on this item. You can not delete this.')
			order.key.delete()
			self.response.write('Order has been deleted')
		else:
			return self.response.write('You do not have the right to edit this order.')
				
class CloseBuyOrder(MyBaseHandler):
	def post(self, order_id):
		order=BuyOrder.get_by_id(int(order_id))
		assert order
		
		# only owner of this order or super can edit
		if order.owner==self.me.key or self.me.can_be_super():
			order.is_closed=True
			order.put()
			self.response.write('Order has been closed')
		else:
			return self.response.write('You do not have the right to close this order.')

class OpenBuyOrder(MyBaseHandler):
	def post(self, order_id):
		order=BuyOrder.get_by_id(int(order_id))
		assert order
		
		# only owner of this order or super can edit
		if order.owner==self.me.key or self.me.can_be_super():
			order.is_closed=False
			order.put()
			self.response.write('Order is now available to sellers')
		else:
			return self.response.write('You do not have the right to open this order.')

class PublishNewBuyOrder(MyBaseHandler):
	def get(self):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		

		# this is used to differentiate new order vs. editing an existing one
		# since we are reusing this template HTML
		self.template_values['order']=None
		
		template = JINJA_ENVIRONMENT.get_template('/template/PublishNewBuyOrder.html')
		self.response.write(template.render(self.template_values))

	def post(self):
		# Assumption: user hits GET first before POST
		# so we don't need to check contact role anymore
		
		# create a new buyorder
		client_email=self.request.POST['client'].strip()
		
		# product name
		# special html symbols have to be converted!
		product=self.request.POST['product'].strip()
		product=product.replace("'",'&#39;')
		product=product.replace('"','&quot;')
		
		# escape newline!
		description=self.request.POST['description'].strip().replace('\r','<br />').replace('\n','<br />')
		
		# to safeguard inputs
		try:
			qty=int(self.request.POST['qty'])
			price=float(self.request.POST['price'])
		except:
			self.response.write('-1')
			return
			
		image=self.request.POST['url'].strip()
		order_id=self.request.get('order_id').strip()
		
		# manage contact -- who is the client, optional
		buyer=None

		if client_email: # if not blank
			b_query=Contact.query(Contact.email==client_email)
			if b_query.count():
				assert b_query.count()==1 # email is unique throughout system!
				buyer=b_query.get()
			else: 
				# no contact yet, create one
				# Note: crearting a Contact this way will 
				buyer=Contact(email=client_email)
				m=Membership(role='Client')
				m.member_pay(0)
				buyer.memberships.append(m)
				buyer.put()
				
		if not order_id:
			# create a new buy order and add to store
			order=BuyOrder()
			order.owner=self.me.key
		else:
			self.template_values['order']=order=BuyOrder.get_by_id(int(order_id))
			
		order.last_modified_by=self.me.key
		if buyer: # buyer info is optional at post
			order.terminal_buyer=buyer.key
		order.name=product
		order.description=description
		order.price=float(price)
		order.qty=int(qty)
		order.image=image
		order.put()
		self.response.write('0')

class BrowseBuyOrderByOwnerByCat(MyBaseHandler):
	def get(self,owner_id,cat):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		

		# load buyorder browse page
		self.template_values['url']=uri_for('buyorder-browse')		

		# filter buyorder by owner
		# and filter by category
		queries=BuyOrder.query(ndb.AND(BuyOrder.owner==ndb.Key(Contact,owner_id), BuyOrder.queues==cat))
		
		# my open cart
		self.template_values['url_cart_review']=uri_for('cart-review')
		
		if len(self.cart.fills):
			# cart has some fills already, we will enforce
			# a filter to display only BuyOrders from the same owner
			# RULE -- unique (intermediate-buyer,terminal-seller) OPEN cart rule
			owner_key = self.cart.fills[0].order.get().owner
			queries=queries.filter(BuyOrder.owner==owner_key)
				
		# compose data structure for template
		self.template_values['buyorders']=queries.order(-BuyOrder.created_time).fetch(100)
				
		template = JINJA_ENVIRONMENT.get_template('/template/BrowseBuyOrder.html')
		self.response.write(template.render(self.template_values))

class BrowseBuyOrderByOwner(MyBaseHandler):
	def get(self,owner_id):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		

		# if you are doc, you are forced to view your own posts ONLY
		# regardless what your request is
		if not self.me.can_be_nur() and self.me.can_be_doc():
			owner_id=self.me.key.id()
		elif not self.me.can_be_nur(): owner_id=None
		self.template_values['owner']=owner_id
		
		# only live and non-0 posts
		orders=BuyOrder.query(ndb.AND(BuyOrder.owner==ndb.Key(Contact,owner_id),BuyOrder.unfilled_qty>0))
		
		# group them by "queues"
		queue={}
		for o in orders:
			# category as dict key
			for q in o.queues:
				if queue.has_key(q): queue[q].append(o)
				else: queue[q]=[o]
		
		self.template_values['cats']=sorted(queue.keys())
		#self.template_values['orders']=queue
		self.template_values['orders']=orders
		template = JINJA_ENVIRONMENT.get_template('/template/BrowseBuyOrderByOwner.html')
		self.response.write(template.render(self.template_values))
		
	def post(self,owner_id):
		# return similar posts from the same owner
		queries=BuyOrder.query(BuyOrder.owner==ndb.Key(Contact,owner_id))
		self.response.write(json.dumps([json.dumps(o.to_dict(),cls=ComplexEncoder) for o in queries]))

class BrowseBuyOrderById(MyBaseHandler):
	def get(self,order_id):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		

		self.template_values['order']=order=BuyOrder.get_by_id(int(order_id))
		assert order
		
		template = JINJA_ENVIRONMENT.get_template('/template/BrowseBuyOrderById.html')
		self.response.write(template.render(self.template_values))

class BrowseBuyOrder(MyBaseHandler):
	def get(self):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		

		# filter by owner id
		try:
			owner_id=self.request.GET['owner']
		except:
			owner_id=None
		self.template_values['owner_id']=owner_id
			
		# filter by Name or Description string match
		try:
			nd=self.request.GET['nd']
		except:
			nd=None

		# list of buyorder to browse
		queries=None
		if not self.me.can_be_nur() and self.me.can_be_doc():
			# I'm a doc but not a nur, only viewable my own posts!
			queries=BuyOrder.query(BuyOrder.owner==self.me.key)
		elif self.me.can_be_nur():
			if len(self.cart.fills):
				# cart has some fills already, we will enforce
				# a filter to display only BuyOrders from the same owner
				# RULE -- unique (broker,terminal-seller) OPEN cart rule
				# thus, overriding owner_id parameter
				owner_id = self.cart.fills[0].order.get().owner.id()
				self.template_values['order_owner']=owner=Contact.get_by_id(owner_id)
			if owner_id and nd:
				# owner_id and nd filters
				queries=BuyOrder.query(ndb.AND(BuyOrder.owner==ndb.Key(Contact,owner_id), BuyOrder.tags.IN(tokenize(nd))), BuyOrder.unfilled_qty>0, BuyOrder.is_closed==False)
				self.template_values['order_owner']=owner=Contact.get_by_id(owner_id)
			elif owner_id:
				# owner_id filter only
				queries=BuyOrder.query(BuyOrder.owner==ndb.Key(Contact,owner_id), BuyOrder.unfilled_qty>0, BuyOrder.is_closed==False)
				self.template_values['order_owner']=owner=Contact.get_by_id(owner_id)
			elif nd:
				# this will be OR tag test, meaning that any tag is in the ND list will be True
				queries=BuyOrder.query(BuyOrder.tags.IN(tokenize(nd)))
			else:
				# no filter
				queries=BuyOrder.query(ndb.AND(BuyOrder.unfilled_qty>0, BuyOrder.is_closed==False))
				
		# compose data structure for template
		if queries:
			queries=queries.fetch(100)
	
		self.template_values['buyorders']=queries		
		template = JINJA_ENVIRONMENT.get_template('/template/BrowseBuyOrder.html')
		self.response.write(template.render(self.template_values))
		
	def post(self):
		# Assumption: user has already hit GET before he can evern POST
		# so we don't need to check Contact here
		
		# add a new buyorder fill to cart 
		buyorder_id=self.request.POST['id']
		price=float(self.request.POST['price'])
		qty=int(self.request.POST['qty']) # allowing negative!

		# get BuyOrder instance
		buyorder=BuyOrder.get_by_id(int(buyorder_id))
		assert buyorder
		
		# we have established an OPEN cart
		existing=False		
		batch=[]
		for i in xrange(len(self.cart.fills)):
			f=self.cart.fills[i]
			if f.order==buyorder.key:
				# it's already in the cart, just update qty
				existing=True
				f.qty+=qty
				
				# update order's filled qty
				order=f.order.get()
				order.filled_qty+= (qty-f.qty)
				batch.append(order)
				
				# update this
				f.last_modified_by=self.me.key
				break
				
		if not existing:
			# if not existing, create a new fill and add to cart
			# default client_price = price so you will break-even
			f=BuyOrderFill(order=buyorder.key,price=price,qty=qty,client_price=price)
			f.owner=self.me.key
			f.last_modified_by=self.me.key
			self.cart.fills.append(f)
			self.cart.broker=buyorder.owner
			
			# update order's filled qty
			order=f.order.get()
			order.filled_qty+= qty
			batch.append(order)
		
		# update cart
		self.cart.put()
		
		# update affected buyorders
		ndb.put_multi(batch)
		
		self.response.write(json.dumps(self.cart.to_dict(),cls=ComplexEncoder))

####################################################
#
# Cart Controllers
#
####################################################

class ApproveCart(MyBaseHandler):
	def post(self,owner_id,cart_id):
		# wow! getting entity directly from key
		# remember that NDB key is a PATH!
		# further, Contact id is String, where everything else id is an INT.
		# this is a big gotcha.
		cart=ndb.Key('Contact',owner_id,'BuyOrderCart',int(cart_id)).get()
		assert cart
		
		batch=[]
		action=self.request.POST['action']
		try:
			seller_notes=self.request.POST['seller_notes']
		except:
			seller_notes=''
		if action.lower()=='submit for approval':
			cart.audit_me(self.me.key,'Status',cart.status,'In Approval')
			cart.status='In Approval'
			cart.seller_notes=seller_notes.strip()
			
			# TODO: send email to all parties here
			send_chat(cart.terminal_seller.get().nickname,cart.broker.get().nickname,'Cart %s by %s needs APPROVAL!' %(cart.key.id(),cart.terminal_seller.get().nickname))
			
		elif action.lower()=='approve' and cart.status=='In Approval':
			cart.audit_me(self.me.key,'Status',cart.status,'Ready for Processing')
			cart.status='Ready for Processing'
			
			# update buyorder approved qty
			for f in cart.fills:
				order=f.order.get()
				order.approved_qty+=f.qty
				batch.append(order)
			ndb.put_multi(batch)
			
			# TODO: send email to all parties here
			send_chat(cart.broker.get().nickname,cart.terminal_seller.get().nickname,'Your cart %s has been APPROVED! Remember to provide the buyer your payment preference.' % cart.key.id())
			
		elif action.lower()=='reject' and cart.status=='In Approval':
			cart.audit_me(self.me.key,'Status',cart.status,'Rejected')
			cart.status='Rejected'

			# TODO: send email to all parties here
			send_chat(cart.broker.get().nickname,cart.terminal_seller.get().nickname,'Your cart %s has been REJECTED!' %cart.key.id())
		
		elif action.lower()=='seller reconcile':
			if cart.can_seller_reconcile(self.me.key):
				cart.audit_me(self.me.key,'Seller Reconciled', cart.seller_reconciled,'True')
				cart.seller_reconciled=True
				
				# TODO: send email to all parties here
				send_chat(cart.terminal_seller.get().nickname,cart.broker.get().nickname,'Seller of cart %s has RECONCILED!' % cart.key.id())
	
				# if buyer reconciled also, close this cart
				if (cart.buyer_reconciled):
					cart.audit_me(self.me.key,'Status',cart.status,'Closed')
					cart.status='Closed'
					
					send_chat('System',cart.broker.get().nickname,'Cart %s is now CLOSED!' % cart.key.id())
					send_chat('System',cart.terminal_seller.get().nickname,'Cart %s is now CLOSED!' %cart.key.id())
		else:
			# TODO: give an assert now
			raise Exception('Unknown path')
				
		cart.last_modified_by=self.me.key
		cart.put()
		self.response.write('0')
		
class ReviewCart(MyBaseHandler):
	def get(self):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		

		cart_id=int(self.request.GET['cart'])

		try:
			owner_id=self.request.GET['owner']
			owner_key=ndb.Key('Contact',owner_id)
			cart=BuyOrderCart.get_by_id(cart_id,parent=owner_key)
		except:		
			cart=BuyOrderCart.get_by_id(cart_id,parent=self.me.key)

		# get cart
		if not cart:
			self.template_values['cart']=None
			template = JINJA_ENVIRONMENT.get_template('/template/ReportIssue.html')
		else:
			assert cart
			self.template_values['shipping_methods']=SHIPPING_METHOD
			self.template_values['cart']=cart
			self.template_values['url']=uri_for('cart-review')
			
			# to save label file using BlobStore
			# owner of the cart is the terminal_seller Contact
			if cart.can_change_shipping(self.me.key):
				self.template_values['shipping_form_url']=upload_url=blobstore.create_upload_url('/cart/shipping/%s/%s/' % (cart.owner.id(),cart.key.id()))
			
			# serve label file if any
			if cart.shipping_label:
				self.template_values['shipping_label']='/blob/serve/%s/'% cart.shipping_label
			else:
				self.template_values['shipping_label']=''
			
			# auditing trail
			if self.request.GET.has_key('audit'):
 				self.template_values['auditing']=MyAudit.query(ancestor=cart.key).order(-MyAudit.created_time)
			
			template = JINJA_ENVIRONMENT.get_template('/template/ReviewCart.html')
		
		# render
		self.response.write(template.render(self.template_values))
	
	def post(self):
		cart_id=int(self.request.POST['cart'])

		try:
			owner_id=self.request.get('owner')
			cart=BuyOrderCart.get_by_id(cart_id,parent=ndb.Key('Contact',owner_id))
		except:
			cart=BuyOrderCart.get_by_id(cart_id,parent=self.me.key)
		assert cart
		status='0'
		
		if self.request.POST.has_key('action'):
			action=self.request.POST['action']
			id=int(self.request.POST['id'])
			obj=self.request.POST['kind']
			batch=[]
			
			if obj=='BuyOrderFill':
				# NOTE: these can only be allowed when cart is still OPEN!
				
				matching_key=ndb.Key('BuyOrder',id)
				
				# we allow remove fill from cart
				if action=='remove':
					new_fills=[f for f in cart.fills if f.order!=matching_key]
					removing=[f for f in cart.fills if f.order==matching_key][0]

					# update cart with new fills
					cart.fills=new_fills
					
					# update removed buyorder filled qty
					order=removing.order.get()
					order.filled_qty -= removing.qty
					batch.append(order)					
					
					# clear cart broker field if all fills are being removed
					if len(new_fills)==0:
						# reset broker field, this is an empty cart
						cart.broker=None
					
				# update client price
				elif action=='update client price':
					price=float(self.request.POST['price'])
					for f in cart.fills:
						if f.order!=matching_key: continue
						f.client_price=price
				
				# update fill price
				elif action=='update fill price':
					price=float(self.request.POST['price'])
					for f in cart.fills:
						if f.order!=matching_key: continue
						f.price=price

				# update fill qty
				elif action=='update fill qty':
					qty=int(self.request.POST['qty'])
					for f in cart.fills:
						if f.order!=matching_key: continue
						# update order's filled qty
						order=f.order.get()
						order.filled_qty+= (qty-f.qty)
						batch.append(order)
						
						# update fill
						f.qty=qty
						
				# update affected order's qty if fill qty changed
				ndb.put_multi(batch)
			
			# update cart
			if len(cart.fills)==0 and cart.status in ['In Approval', 'Rejected']:
				# if this is editing from a REJECTED cart, there may already be another OPEN
 				# cart! So we can not return this cart to OPEN. Rather, in this case, this cart should be deleted!
				# delete this cart
				cart.key.delete()
				status='-1'
			else: 
				cart.put()
				
				# we now have an empty cart, should ask client to redirect to browse window
				if len(cart.fills)==0: status='-2'
			self.response.write(status)

	
class ManageCartAsSeller(MyBaseHandler):
	def get(self):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		

		self.template_values['review_url']=uri_for('cart-review')		
		
		# get all carts that belong to this user
		# these are ones user has file as a Nur
		self.template_values['my_carts']=BuyOrderCart.query(ancestor=self.me.key).filter(BuyOrderCart.status!='Open').order(BuyOrderCart.status,-BuyOrderCart.last_modified_time)

		# render
		template = JINJA_ENVIRONMENT.get_template('/template/ManageCartAsSeller.html')
		self.response.write(template.render(self.template_values))

class ManageCartAsBuyer(MyBaseHandler):
	def get(self):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		

		self.template_values['review_url']=uri_for('cart-review')		
		
		# get all carts that this user is the broker
		# these are ones need approval
		orders=BuyOrderCart.query(BuyOrderCart.broker==self.me.key).filter(BuyOrderCart.status!='Closed').order(BuyOrderCart.status,-BuyOrderCart.last_modified_time)
		self.template_values['broker_carts']=[o for o in orders if o.status!='Open']
		
		# render
		template = JINJA_ENVIRONMENT.get_template('/template/ManageCartAsBuyer.html')
		self.response.write(template.render(self.template_values))
	
		
####################################################
#
# Shipping Process Controllers
#
####################################################

class ShippingCartProcess(MyBaseHandler):
	def post(self,owner_id,cart_id):
		cart=ndb.Key('Contact',owner_id,'BuyOrderCart',int(cart_id)).get()
		assert cart
		
		# by setting up this, I'm allowing shipping-date to be updated
		# independently from shipping_status
		# however, on UI, the input is only available when cart can be In Route
		if self.request.POST.has_key('shipping date'):
			# update shipping date
			try:
				new_date=datetime.datetime.strptime(self.request.POST['shipping date'],'%Y-%m-%d').date()
			except:
				new_date=datetime.datetime.strptime(self.request.POST['shipping date'],'%m/%d/%Y').date()
			cart.audit_me(self.me.key,'Shipping Date',cart.shipping_date,new_date)
			cart.shipping_date=new_date

			# TODO: email all parties
			send_chat(cart.terminal_seller.get().nickname,cart.broker.get().nickname,'Cart %s has been SHIPPED by %s!' %(cart.key.id(),cart.owner.get().nickname))
		    
		cart.audit_me(self.me.key,'Shipping Status',cart.shipping_status,self.request.POST['action'])
		cart.shipping_status=self.request.POST['action']
		if cart.shipping_status == 'In Dispute':
			cart.status='Shipment In Dispute'
			
			# TODO: create case to dispute this cart
			
		elif cart.shipping_status == 'Destination Reconciled':
			cart.status='Shipment Clean'

			# set buyer reconciled flag
			# auditing trail will record timestamp
			cart.audit_me(self.me.key,'Buyer Reconciled',cart.buyer_reconciled,True)
			cart.buyer_reconciled=True
			
			send_chat(cart.broker.get().nickname,cart.terminal_seller.get().nickname,'Buyer of cart %s has RECONCILED!' % cart.key.id())

			# if buyer reconciled also, close this cart
			if (cart.seller_reconciled):
				cart.audit_me(self.me.key,'Status',cart.status,'Closed')
				cart.status='Closed'

				send_chat('System',cart.broker.get().nickname,'Cart %s is now CLOSED!' % cart.key.id())
				send_chat('System',cart.terminal_seller.get().nickname,'Cart %s is now CLOSED!' % cart.key.id())
			
		cart.put()	
			
				
class ShippingCart(blobstore_handlers.BlobstoreUploadHandler):
	def post(self, owner_id,cart_id):
		user = users.get_current_user()
		me=Contact.get_or_insert(ndb.Key('Contact',user.user_id()).string_id(),
			email=user.email(),
			nickname=user.nickname())

		cart=ndb.Key('Contact',owner_id,'BuyOrderCart',int(cart_id)).get()
		assert cart
		assert cart.broker==me.key

		cart.shipping_carrier=self.request.POST['shipping-carrier']
		cart.shipping_tracking_number=self.request.POST['shipping-tracking']
		cart.shipping_num_of_package=int(self.request.POST['shipping-package'])
		
		# cost is optional
		# if broker already know how much this label costs him, ie. a flat rate
		# then he can choose to enter here
		# otherwise, he will be able to edit the cost field anytime after shipment is created
		cart.shipping_cost=float(self.request.POST['shipping-cost'])

		# this date is updated everytime
		# because actions like an notification email will take place
		# when something is changed
		cart.shipping_created_date=datetime.date.today()
		
		# shipping label is optional
		# think about USPS
		uploads=self.get_uploads('shipping-label')
		if len(uploads):
			blob_info = uploads[0]
			if cart.shipping_label:
				# if there is existing
				# delete this from blobstore
				# NOTE: blobstore can not overwrite, but can delete
				delete(cart.shipping_label)
			
			# now save new blob key
			cart.shipping_label=blob_info.key()
			
			# TODO: email seller label ready!
			
		cart.shipping_status='Shipment Created'
		cart.status='In Shipment'
		cart.put()	

		# notify seller
		send_chat(cart.broker.get().nickname,cart.terminal_seller.get().nickname,'Buyer has created shipping information. Cart %s is ready for SHIPPIING!' % cart.key.id())

		self.response.write('0')
		
####################################################
#
# User/Membership Controllers
#
####################################################

class MyUserBaseHandler(MyBaseHandler):
	def __init__(self, request=None, response=None):
		MyBaseHandler.__init__(self,request,response) # extend the base class

class ManageUserMembership(MyUserBaseHandler):
	def get(self):
		self.template_values['membership_options']=self.me.get_eligible_memberships()
			
		# render
		template = JINJA_ENVIRONMENT.get_template('/template/ManageUserMembership.html')
		self.response.write(template.render(self.template_values))

class ManageUserMembershipCancel(MyUserBaseHandler):
	def post(self,role):	
		self.me.cancel_membership(role)
				
		# update Contact
		self.response.write('0')

class ManageUserContact(MyBaseHandler):
	def get(self):	
		#try:
		if self.me.can_be_super():
			self.template_values['me']=Contact.get_by_id(self.request.get('id'))
			logging.debug('person identity swap')
		else: pass
		#except: pass
		# render
		template = JINJA_ENVIRONMENT.get_template('/template/ManageUserContact.html')
		self.response.write(template.render(self.template_values))

	def post(self):
		self.me.communication=self.request.POST
		self.me.put()
		
		for k,value in self.me.communication.iteritems():
			if k.lower().strip()=='mitbbs':
				send_chat(self.me.nickname,'System','%s (%s) is requesting MITBBS id %s' % (self.me.nickname,self.me.email,value))
		self.response.write('0')

class ManageUserContactPreference(MyBaseHandler):
	def post(self):
		self.me.shipping_preference=self.request.POST['shipping']
		self.me.payment_preference=self.request.POST['payment']
		self.me.put()
		self.response.write('0')

class ViewUserRiskProfile(MyBaseHandler):
	def post(self):
		# get all outstanding buyorders
		orders=BuyOrder.query(ndb.AND(BuyOrder.is_closed==False,BuyOrder.unfilled_qty>0))
		
		# group by owner/broker
		group_by_owner={}
		for o in orders:
			if o.owner not in group_by_owner:
				group_by_owner[o.owner]=[o]
			else:
				group_by_owner[o.owner].append(o)
		
		# get chart data
		data=[]
		for owner,orders in group_by_owner.iteritems():
			total_payable=sum([o.payable for o in orders])
			data.append({
				'name':owner.get().nickname,
				'ownerId':owner.id(),
				'data':[[total_payable,len(orders),owner.get().reputation_score+100]]
			})
		self.response.write(json.dumps(data))
		
####################################################
#
# Google Wallet Controllers
#
####################################################
class GoogleWalletToken(MyBaseHandler):
	def post(self):
		requesting_role=self.request.get('role')
		jwt_token = jwt.encode(
  			{
  			"iss" : GOOGLE_SELLER_ID,
  			"aud" : "Google",
  			"typ" : "google/payments/inapp/item/v1",
  			"exp" : int(time.time() + 3600),
  			"iat" : int(time.time()),
  			"request" :{
				"name" : "%s Membership for %s" % (requesting_role,self.me.nickname),
  				"description" : "%s membership subscriptions" % requesting_role,
				"price" : MONTHLY_MEMBERSHIP_FEE[requesting_role],
  				"currencyCode" : "USD",
				"sellerData" : "%s" % self.me.key.id(),
				"initialPayment" : {
  					"price" : MONTHLY_MEMBERSHIP_FEE[requesting_role],
					"currencyCode" : "USD",
  					"paymentType" : "prorated",
  				},
  				"recurrence" : {
					"price" : MONTHLY_MEMBERSHIP_FEE[requesting_role],
  					"currencyCode" : "USD",
					"startTime" : int(time.time() + 2600000),
  					"frequency" : "monthly",
					"numRecurrences" : "12",
				}				
			}
  			},
			GOOGLE_SELLER_SECRET)
		self.response.write(jwt_token)
		
class GoogleWalletPostback(webapp2.RequestHandler):
	def post(self):
		encoded_jwt = self.request.get('jwt')
		if encoded_jwt is not None:
  			result = jwt.decode(str(encoded_jwt), GOOGLE_SELLER_SECRET)
  		
		# validate the payment request and respond back to Google
  		if result['iss'] == 'Google' and result['aud'] == GOOGLE_SELLER_ID:
  			if ('response' in result and
  				'orderId' in result['response'] and
  				'request' in result):
				
				order_id = result['response']['orderId']
  				request_info = result['request']
				contact_id=result['request']['sellerData']

				# look up Contact
				contact=Contact.get_by_id(contact_id)
				assert contact
				
				# updat Contact memberships
				role=result['request']['name']
				role=role[:3] # strip off " Membership"
				
				# no status code, normal transaction
				# create a separate order record
				google_order=GoogleWalletSubscriptionOrder(parent=ndb.Key('DummyAncestor','WalletRoot'),
					role=role, 
					order_id=order_id,
					order_detail=json.dumps(result),
					contact_key=contact.key)
				google_order.put()			

				# update Contact
				contact.signup_membership(google_order)
					
  				# respond back to complete payment
  				self.response.out.write(order_id)

			
			# check if this was a subscription cancellation postback
			if ('response' in result and
				'orderId' in result['response'] and
				'statusCode' in result['response']):
  				
  				order_id=result['response']['orderId']
  				status_code =  result['response']['statusCode']
				if status_code == 'SUBSCRIPTION_CANCELED':
					# there is status code
					# cancellation
					GoogleWalletSubscriptionOrder.cancel_membership_by_wallet(order_id)
			
####################################################
#
# Report Controllers
#
####################################################

class ReportMyIncome(MyBaseHandler):
	def get(self,in_days):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		
		
		self.template_values['filter_days']=in_days
		self.template_values['end']=datetime.date.today()
		self.template_values['start']=datetime.date.today()+datetime.timedelta(-1*int(in_days))
		
		# get all my slips
		# slips party "a" is always the one who initiated it
		# you can also use the "owner" key, it's the same
		if self.me.can_be_doc():
			# if you are doc, you view both in and out
			slips=AccountingSlip.query(ancestor=ndb.Key(DummyAncestor,'BankingRoot')).filter(ndb.AND(ndb.OR(AccountingSlip.party_a==self.me.key,AccountingSlip.party_b==self.me.key),AccountingSlip.age<=float(in_days)*24*3600)).order(-AccountingSlip.age)
		elif self.me.can_be_nur():
			# if you are nur, you are party b
			slips=AccountingSlip.query(ancestor=ndb.Key(DummyAncestor,'BankingRoot')).filter(ndb.AND(AccountingSlip.party_b==self.me.key,AccountingSlip.age<=float(in_days)*24*3600)).order(-AccountingSlip.age)
			
		# ending balance
		ending=self.me.cash
		
		# beginning balance
		transactions=[]
		for s in slips:
			if s.party_a==self.me.key:
				if s.money_flow=='a-2-b': # I'm A and money is to B
					# money go out
					transactions.append(-1*s.amount)
				else:
					# money come in
					transactions.append(s.amount)
			elif s.party_b==self.me.key: # flip logic from above
				if s.money_flow=='a-2-b': # I'm B and money from A
					# money come in
					transactions.append(s.amount)
				else:
					# money go out
					transactions.append(-1*s.amount)
		beginning=ending-sum(transactions)
		
		data=[beginning]
		for t in transactions:
			# aggregated income growth
			data.append(data[-1]+t)
		data.append(ending)
		self.template_values['beginning']=beginning
		self.template_values['ending']=ending
		self.template_values['data']=json.dumps(data)
		
		# render
		self.template_values['slips']=slips
		template = JINJA_ENVIRONMENT.get_template('/template/ReportMyIncome.html')
		self.response.write(template.render(self.template_values))

class ReportMyBuyer(MyBaseHandler):
	def get(self, in_days):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		

		self.template_values['filter_days']=in_days
		self.template_values['end']=datetime.date.today()
		self.template_values['start']=datetime.date.today()+datetime.timedelta(-1*int(in_days))
		
		# we are to determine who is a good buyer (Doc) to do business with
		
		# get all shopping carts that I'm a seller  -- Nur within the last [in_days]
		# NOTE: do not include OPEN cart because open cart broker=None
		carts=BuyOrderCart.query(BuyOrderCart.terminal_seller==self.me.key,BuyOrderCart.age<=float(in_days)*24*3600)
		carts=[c for c in carts if c.broker]
		self.template_values['carts']=carts
		
		# group by broker
		brokers={}
		for c in carts:
			s=c.broker
			if s not in brokers: brokers[s]=[c]
			else: brokers[s].append(c)
			
		# this represents size of a deal
		# Q: who is your large supplier?
		payable={}
		for s in brokers:
			payable[s]=sum([a.payable for a in brokers[s]])
		self.template_values['payable']=payable
		self.template_values['payable_chart_data']=json.dumps([(s.get().nickname, payable[s]) for s in payable])
		
		# render
		template = JINJA_ENVIRONMENT.get_template('/template/ReportMyBuyer.html')
		self.response.write(template.render(self.template_values))
		
class ReportMySeller(MyBaseHandler):
	def get(self, in_days):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		

		self.template_values['filter_days']=in_days
		self.template_values['end']=datetime.date.today()
		self.template_values['start']=datetime.date.today()+datetime.timedelta(-1*int(in_days))
		
		# we are to determine who is a good seller (Nur) to do business with
		
		# get all shopping carts that I'm a buyer  -- Doc
		# including open ones within the last [in_days]
		# NOTE: must use float for comparison, otherwise it will return None
		carts=BuyOrderCart.query(BuyOrderCart.broker==self.me.key,BuyOrderCart.age<=float(in_days)*24*3600)
		self.template_values['carts']=carts
		
		# group by sellers
		sellers={}
		for c in carts:
			s=c.terminal_seller
			if s not in sellers: sellers[s]=[c]
			else: sellers[s].append(c)
			
		# this represents size of a deal
		# Q: who is your large supplier?
		payable={}
		for s in sellers:
			payable[s]=sum([a.payable for a in sellers[s]])
		self.template_values['payable']=payable
		self.template_values['payable_chart_data']=json.dumps([(s.get().nickname, payable[s]) for s in payable])
		
		# render
		template = JINJA_ENVIRONMENT.get_template('/template/ReportMySeller.html')
		self.response.write(template.render(self.template_values))
		
class ReportBuyOrderPopular(MyBaseHandler):
	def get(self,in_days):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		

		self.template_values['filter_days']=in_days
		self.template_values['end']=datetime.date.today()
		self.template_values['start']=datetime.date.today()+datetime.timedelta(-1*int(in_days))
		
		# get all carts that I'm the buyer
		# including open ones within the last [in_days]
		# NOTE: must use float for comparison, otherwise it will return None
		carts=BuyOrderCart.query(BuyOrderCart.broker==self.me.key,BuyOrderCart.age<=float(in_days)*24*3600)
		self.template_values['carts']=carts

		payable={}
		fills=[]
		for c in carts:
			fills+=c.fills
			for f in c.fills:
				if f.order in payable: payable[f.order] += f.payable
				else: payable[f.order]=f.payable
		self.template_values['payable']=payable
		self.template_values['payable_chart_data']=json.dumps([(s.get().name, payable[s]) for s in payable])
		self.template_values['fills']=fills
		
		# render
		template = JINJA_ENVIRONMENT.get_template('/template/ReportBuyOrderPopular.html')
		self.response.write(template.render(self.template_values))


####################################################
#
# Channel controllers
#
####################################################

def send_chat(sender,receiver,message):
		# look up live receiver channel by name
		queries=ChatChannel.query(ChatChannel.contact_name==receiver, ChatChannel.in_use==True)
		
		if queries.count()>0:
			for c in queries:
				# receiver live channel found
				channel.send_message(c.client_id,json.dumps({'sender':sender,'message':message}))
			return queries.count()
		else:
			# no live channel to receiver, we send an email alert
			if sender.lower in ['system','admin','anthem.marketplace']:
				from_email='anthem.marketplace@gmail.com'
			else:
				sender=Contact.query(Contact.nickname==sender).get()
				if sender: from_email=sender.email
				else: from_email=None
			
			if receiver.lower() in ['system','admin', 'anthem.marketplace']:
				to_email='anthem.marketplace@gmail.com'
			else:
				receiver=Contact.query(Contact.nickname==receiver).get()
				if receiver: to_email=receiver.email
				else: to_email=None
			
			# if there is a valid receiver email
			if from_email and to_email:
				# user may put in a typo, so we use this IF instead of assert
				mail.send_mail(sender=from_email,
					to=to_email,
					subject="You have got mail",
					body=message
				)
			return 0
			

class ChannelConnected(webapp2.RequestHandler):
	def post(self):
		client_id=self.request.get('from')
		queries=ChatChannel.query(ChatChannel.client_id==client_id)
		if queries.count()==0: return
		
		assert queries.count()==1
		saved_channel=queries.get()
		
		# check channel age
		# max 2-hour
		if saved_channel.is_expired: 
			saved_channel.key.delete()
			
			# tell client this channel has expired
			self.response.write('-1')
			return
			
		# set channel to in_use
		saved_channel.in_use=True
		saved_channel.put()	
		
						
class ChannelDisconnected(webapp2.RequestHandler):
	def post(self):
		client_id=self.request.get('from')
		
		queries=ChatChannel.query(ChatChannel.client_id==client_id)
		if queries.count()==0: return

		assert queries.count()==1
		saved_channel=queries.get()

		# check channel age
		# max 2-hour
		if saved_channel.is_expired: 
			saved_channel.key.delete()
			
			# tell client this channel has expired
			self.response.write('-1')
			return
			
		# set channel to in_use
		saved_channel.in_use=False
		saved_channel.put()	
		
		
class ChannelToken(webapp2.RequestHandler):
	# This is the token pool management controller.
	# client page will POST to request a token to use
	# we will look up the pool for usable channel, if nothing, we'll create a new one.
	# Further, a client_id can have max 2 open channels -- this essentially limits
	# how many browser tabs a user can open while still have a usable chat on that page.
	def post(self):
		# who is requesting?
		contact_id=self.request.get('contact_id')
		contact_name=self.request.get('contact_name')
		
		# let's find a channel for this user
		token=None
		opened_channel_count=0
		
		all_saved_channel=ChatChannel.query()
		queries=all_saved_channel.filter(ChatChannel.contact_id==contact_id)
		for c in queries:
			if c.in_use is False:
				# unused channel, validate its age
				if c.is_expired:
					c.key.delete()
				else: 
					token=c.token
					break # we found a valid token to use
			else: opened_channel_count +=1
				
		# no reusable channel for this contact_id
		if token is None:
			if all_saved_channel.count()>=100:
				# we have hit the max quota, tell user he can not chat, sorry
				self.response.write('-2')
			elif opened_channel_count <2:
				# create a new one
				# has quota, create one and add to the pool
				random_id=contact_id+id_generator()
				random_token = channel.create_channel(random_id)
				 
				# add to pool
				c=ChatChannel(client_id=random_id, contact_id=contact_id,contact_name=contact_name,token=random_token)
				c.put()
				 
				# tell client token
				self.response.write(random_token)
			
			else: # user has 2 open channel already, deny new request
				self.response.write('-1')
		else:
			logging.info('Reuse token: '+token)
			self.response.write(token)
				
class ChannelRouteMessage(webapp2.RequestHandler):
	def post(self):
		sender=self.request.get('sender').strip()
		receiver=self.request.get('receiver').strip()[1:]
		message=self.request.get('message').strip()
		
		# user offline
		if send_chat(sender,receiver,message)==0:
			self.response.write('-1')

class ChannelListOnlineUsers(webapp2.RequestHandler):
	def post(self):
		queries=ChatChannel.query(ChatChannel.in_use==True)
		online_users=list(set([c.contact_name for c in queries]))
		if len(online_users):
			self.response.write(json.dumps(online_users))
		else: self.response.write('-1')
		

####################################################
#
# Banking Controllers
#
####################################################

class DeleteBankSlip(MyBaseHandler):
	def post(self, slip_id):
		slip=AccountingSlip.get_by_id(int(slip_id),parent=ndb.Key('DummyAncestor','BankingRoot'))
		assert slip

		# update cart		
		cart=slip.cart_key.get()
		cart.payout_slips=[c for c in cart.payout_slips if c != slip.key]		
		cart.payin_slips=[c for c in cart.payin_slips if c != slip.key]
		cart.put()
		
		# update contact cash account
		# this is the reverse of when slip was created
		# remember, cart broker is always party_a!
		party_a=slip.party_a.get()
		party_b=slip.party_b.get()
		if slip.money_flow == 'a-2-b':
			# this was a payout
			party_a.cash+=slip.amount
			party_b.cash-=slip.amount
		elif slip.money_flow=='b-2-a':
			# this was a payin
			party_a.cash-=slip.amount
			party_b.cash+=slip.amount
		
		party_a.put()
		party_b.put()
		self.response.write('0')

class BankingCart(MyBaseHandler):
	def get(self):
		if not self.me.is_active:
			template = JINJA_ENVIRONMENT.get_template('/template/Membership_New.html')
			self.response.write(template.render(self.template_values))
			return		

		self.template_values['url']=uri_for('cart-banking')
		self.template_values['review_url']=uri_for('cart-review')		
	
		# payable carts
		payable_carts=BuyOrderCart.query(ndb.AND(BuyOrderCart.broker==self.me.key,BuyOrderCart.payable_balance>0.0))
		
		if self.request.GET.has_key('seller'):
			seller_id=self.request.GET['seller']
			payable_carts=payable_carts.filter(BuyOrderCart.terminal_seller==ndb.Key('Contact',seller_id))
		self.template_values['payable_carts']=payable_carts
		self.template_values['sellers']=set([c.terminal_seller for c in payable_carts])
		
		# receivable carts
		receivable_carts=BuyOrderCart.query(ndb.AND(BuyOrderCart.broker==self.me.key,BuyOrderCart.receivable_balance>0.0))
		if self.request.GET.has_key('client'):
			client_id=self.request.GET['client']
			receivable_carts=receivable_carts.filter(BuyOrderCart.terminal_buyer==ndb.Key('Contact',client_id))				
		self.template_values['receivable_carts']=receivable_carts
		self.template_values['clients']=set([c.terminal_buyer for c in receivable_carts if c.terminal_buyer])
		
		# render
		template = JINJA_ENVIRONMENT.get_template('/template/BankingCart.html')
		self.response.write(template.render(self.template_values))
	
	def post(self):
		status='0'
		
		action=self.request.POST['action']
		data=json.loads(self.request.POST['data'])
		bundle=[]
				
		if action=='payable':
			# convert ID to INT, because datastore uses INT, not string!
			payables={int(d['id']):d['amount'] for d in data}			
			carts=BuyOrderCart.query(ndb.AND(BuyOrderCart.broker==self.me.key,BuyOrderCart.payable_balance>0))
			cart_dict={c.key.id():(c,payables[c.key.id()]) for c in carts if c.key.id() in payables}
			
			for id,val in cart_dict.iteritems():
				cart,pay=val
				
				# create a slip
				slip=AccountingSlip(parent=ndb.Key(DummyAncestor,'BankingRoot'))
				slip.amount=float(pay)
				slip.party_a=self.me.key
				slip.party_b=cart.terminal_seller
				slip.money_flow='a-2-b'
				slip.last_modified_by=self.me.key
				slip.owner=self.me.key
				slip.cart_key=cart.key
				slip.put() # has to save here, otherwise, cart update will fail for computed property being None!

				# notify
				send_chat(cart.broker.get().nickname,cart.terminal_seller.get().nickname,'Buyer of cart %s has added a PAYMENT!' % cart.key.id())
				
				# create an audit record
				slip.audit_me(self.me.key,'Cart Status',cart.status,'')
				slip.audit_me(self.me.key,'Shipping Status',cart.shipping_status,'')
				
				# add to cart
				# cart only wants the slip key!
				cart.payout_slips.append(slip.key)
				
				# payouts, deduct this amount from my contact
				self.me.cash-=float(pay)
				self.me.put()
				
				seller=cart.terminal_seller.get()
				seller.cash+=float(pay)
				seller.put()
				
				# notify
				send_chat('System',cart.terminal_seller.get().nickname,'%s has added to your cash account!' %(str(pay)))

				# we will update cart later
				bundle.append(cart)
				
		elif action=='receivable':
			# convert ID to INT, because datastore uses INT, not string!
			receivables={int(d['id']):d['amount'] for d in data}			
			carts=BuyOrderCart.query(ndb.AND(BuyOrderCart.broker==self.me.key,BuyOrderCart.receivable_balance>0))
			cart_dict={c.key.id():(c,receivables[c.key.id()]) for c in carts if (c.key.id() in receivables)}
			
			for id,val in cart_dict.iteritems():
				cart,pay=val
				# create a slip
				slip=AccountingSlip(parent=ndb.Key(DummyAncestor,'BankingRoot'))
				slip.amount=float(pay)
				slip.party_a=self.me.key
				slip.party_b=cart.terminal_buyer
				slip.money_flow='b-2-a'
				slip.last_modified_by=self.me.key
				slip.owner=self.me.key
				slip.cart_key=cart.key
				slip.put() # has to save here!

				# create an audit record
				slip.audit_me(self.me.key,'Cart Status',cart.status,'')
				slip.audit_me(self.me.key,'Shipping Status',cart.shipping_status,'')
						
				# add to cart
				# cart only wants the slip key!
				cart.payin_slips.append(slip.key)
				
				# update contact account balance
				self.me.cash+=float(pay)
				self.me.put()
				
				if (cart.terminal_buyer):
					buyer=cart.terminal_buyer.get()
					buyer.cash-=float(pay)
					buyer.put()			
				
				# add cart to bundel
				bundle.append(cart)
			
		ndb.put_multi(bundle)
		
		# return status
		self.response.write(status)

