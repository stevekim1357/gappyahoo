import babel.dates
import urllib2
import logging
from dateutil.relativedelta import relativedelta
import datetime
import string,random
from pprint import pprint,pformat
from collections import Counter # awesome!
from lxml import html
from lxml.html.clean import clean_html
from urlparse import urlparse
import feedparser

def myRSSParser(url):


def myHTMLParser(url,css,length,depth,current_depth,hit_list):
	if url in hit_list: return ([],[])
	
	result=[]
	hit_list.append(url)
	
	rr=urlparse(url)
	sub_links=[]
	content=''
	
	try:
		conn=urllib2.urlopen(url)
		page=conn.read()
		conn.close()
		
		# clean up html		
		data=clean_html(page)
		tree=html.fromstring(data)
		
		# get all href links
		links=[link for element, attribute, link, pos in tree.iterlinks() if attribute=='href']
		for l in links:
			if l.startswith('http'): sub_links.append(l)
			elif l.startswith('/'): sub_links.append('%s://%s%s' % (rr.scheme, rr.netloc,l))
		sub_links=list(set(sub_links)) # unique list
			
		# get text contents on this page
		if '#' in css:
			# a single ID in the page
			content=tree.cssselect(css)[0].text_content()	
		elif '.' in css:
			# a CSS class
			content=' '.join([i.text_content() for i in tree.cssselect(css)])		
		else:
			# if no CSS preference, select the very first DIV in the page
			# this is the catch-all scenario, especially when iterating links
			content=tree.cssselect('div')[0].text_content()

		# update crawl result master list
		if content: 
			result=[content]
	except:
		pass	
	
	# follow links
	if int(current_depth) < int(depth):
	#if int(current_depth) <= 1:
		for l in sub_links:
			if l in hit_list: continue
			
			logging.info('next: '+l)
			logging.info('length: '+str(length))
			logging.info('depth: '+str(depth))
			logging.info('current: '+str(current_depth))
			
			pprint('next: '+l)
			pprint('length: '+str(length))
			pprint('depth: '+str(depth))
			pprint('current: '+str(current_depth))
		
			r,h=myHTMLParser(l,'',length,depth,current_depth+1,hit_list)
			result+=r
			hit_list=list(set(hit_list+h))
	# return
	return (result,hit_list)
		
		
def format_datetime(value, format='medium'):
	if format == 'full':
		format="EEEE, d. MMMM y 'at' HH:mm"
	elif format == 'medium':
		format="EE dd.MM.y HH:mm"
	return babel.dates.format_datetime(value, format)

def id_generator(size=12, chars=string.ascii_uppercase + string.digits):
	return ''.join(random.choice(chars) for x in range(size))
