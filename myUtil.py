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
from collections import Counter
import nltk # assuming this available
from nltk.tokenize.punkt import PunktSentenceTokenizer, PunktParameters

def myNLTKParser(document):
	lexical_diversity=len(document) / len(set(document))*1.0
	
	# POS tags
	punkt_param = PunktParameters()
	# if any customized abbrev
	#punkt_param.abbrev_types = set(['dr', 'vs', 'mr', 'mrs', 'prof', 'inc'])
	
	sentence_splitter = PunktSentenceTokenizer(punkt_param)
	sentences = sentence_splitter.tokenize(document)
	word_tokens=[nltk.word_tokenize(s) for s in sentences]
		
	tags=[nltk.pos_tag(a) for a in word_tokens]
	merged_tags = [word for sublist in tags for (word,tag) in sublist if tag in ['JJ','JJR','JJS','NN','NNP','NNPS','NNS','RB','RBR','RBS']]
	tags_fd=nltk.FreqDist(merged_tags)

	return tags_fd,tags
	
def myRssParser(source):
	if source.keywords and source.etag:
		#feed=feedparser.parse(source.feed_url,etag=source.etag)
		feed=feedparser.parse(source.feed_url)
		if feed['status']==304: return [] # no new update
	else:
		feed=feedparser.parse(source.feed_url)
		if feed['status']!=200: return None # error
		
	# update source record
	source.name=feed['feed']['title']
	source.root_link=feed['feed']['link']
	source.etag=feed['etag']
	source.put()
	
	# get feed contents
	content=[]
	for i in feed['items']:
		title=i['title']
		detail_link=i['id']
		text_content=''
		
		# get linked content
		conn=urllib2.urlopen(i['id'])
		page=conn.read()
		conn.close()

		# clean up html		
		data=clean_html(page)
		tree=html.fromstring(data)
		if 'Reuters' in source.name:
			text_content=' '.join([j.text_content() for j in tree.cssselect('span#articleText p')])		
		
		fd,tags=myNLTKParser(text_content)
		logging.info(fd.max())
				
		# data
		content.append({'headline':title, 'link':detail_link, 'text':text_content, 'fd_max':fd.max(),'pos_tags':tags, 'tags_fd':fd})
	
	# nltk sentiments
	#for c in content:
	#	rss=nltk.Text(nltk.word_tokenize(c['headline']))

	return content
	
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
