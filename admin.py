import webapp2
from google.appengine.api import users
from google.appengine.ext import blobstore
from google.appengine.api import images
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext.blobstore import delete, delete_async
from google.appengine.api import channel
from google.appengine.api import mail
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
import lxml
from models import *
from myUtil import *
from secrets import *

JINJA_ENVIRONMENT = jinja2.Environment(
	loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
	extensions=['jinja2.ext.autoescape'])
                
                
class MyBaseHandler(webapp2.RequestHandler):
	def __init__(self, request=None, response=None):
		webapp2.RequestHandler.__init__(self,request,response) # extend the base class
		self.template_values={}         
		self.template_values['user']=self.user = users.get_current_user()
		self.template_values['url_login']=users.create_login_url(self.request.url)
		self.template_values['url_logout']=users.create_logout_url('/')

class AdminContactHandler(MyBaseHandler):
	def get(self):
		# get all contacts
		self.template_values['contacts']=contacts=Contact.query()
		template = JINJA_ENVIRONMENT.get_template('/template/AdminContact.html')
		self.response.write(template.render(self.template_values))
				
	def post(self):
		contact_id=self.request.get('contact id')
		role=self.request.get('role')
		contact=Contact.get_by_id(contact_id)
		assert contact
		contact.cancel_membership(role)
		
		self.response.write('0')

class AdminNewsSourceHandler(MyBaseHandler):
	def get(self):
		# get all source
		self.template_values['sources']=news_sources=NewsSource.query()
		template = JINJA_ENVIRONMENT.get_template('/template/AdminNewsSource.html')
		self.response.write(template.render(self.template_values))
	
	def post(self):
		action=self.request.get('action')
		if action=='add':
			url=self.request.get('url')
			source=self.request.get('source')
			css_selector=self.request.get('css')
			length=int(self.request.get('length'))
			depth=int(self.request.get('link'))
		
			s=NewsSource(url=url,source=source,css_selector=css_selector,length_of_interest=length,link_depth=depth)
			s.put()
		elif action=='delete':
			id=int(self.request.get('id'))
			s_key=ndb.Key('NewsSource',id)
			s_key.delete()
			
		self.response.write('0')
