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
from nltk.stem.porter import PorterStemmer
import nltk.chunk
import itertools

# http://www.textfixer.com/resources/common-english-words.php
stopwords='''
a,able,about,across,after,all,almost,also,am,among,an,and,any,are,as,at,be,because,been,but,by,can,cannot,could,dear,did,do,does,either,else,ever,every,for,from,get,got,had,has,have,he,her,hers,him,his,how,however,i,if,in,into,is,it,its,just,least,let,like,likely,may,me,might,most,must,my,neither,no,nor,not,of,off,often,on,only,or,other,our,own,rather,said,say,says,she,should,since,so,some,than,that,the,their,them,then,there,these,they,this,tis,to,too,twas,us,wants,was,we,were,what,when,where,which,while,who,whom,why,will,with,would,yet,you,your,
'tis, 'twas, a, able, about, across, after, ain't, all, almost, also, am, among, an, and, any, are, aren't, as, at, be, because, been, but, by, can, 
can't, cannot, could, could've, couldn't, dear, did, didn't, do, does, doesn't, don't, either, else, ever, every, for, from, get, got, had, has, 
hasn't, have, he, he'd, he'll, he's, her, hers, him, his, how, how'd, how'll, how's, however, i, i'd, i'll, i'm, i've, if, in, into, is, isn't, it, 
it's, its, just, least, let, like, likely, may, me, might, might've, mightn't, most, must, must've, mustn't, my, neither, no, nor, not, of, off, 
often, on, only, or, other, our, own, rather, said, say, says, shan't, she, she'd, she'll, she's, should, should've, shouldn't, since, so, some, 
than, that, that'll, that's, the, their, them, then, there, there's, these, they, they'd, they'll, they're, they've, this, tis, to, too, twas, us, 
wants, was, wasn't, we, we'd, we'll, we're, were, weren't, what, what'd, what's, when, when, when'd, when'll, when's, where, where'd, where'll, 
where's, which, while, who, who'd, who'll, who's, whom, why, why'd, why'll, why's, will, with, won't, would, would've, wouldn't, yet, you, you'd, 
you'll, you're, you've, your,.,",$,
'''
stopwords=set([w.strip() for w in stopwords.split(',')]+[','])

 
class TagChunker(nltk.chunk.ChunkParserI):
	def __init__(self, chunk_tagger):
		self._chunk_tagger = chunk_tagger
  
	def parse(self, tokens):
		# split words and part of speech tags
		(words, tags) = zip(*tokens)

		# get IOB chunk tags
		chunks = self._chunk_tagger.tag(tags)

		# join words with chunk tags
		wtc = itertools.izip(words, chunks)
		
		# w = word, t = part-of-speech tag, c = chunk tag
		lines = [' '.join([w, t, c]) for (w, (t, c)) in wtc if c]
		
		# create tree from conll formatted chunk lines
		return nltk.chunk.conllstr2tree('\n'.join(lines))
  
def myNLTKParser(document,tagger):
	lexical_diversity=len(document) / len(set(document))*1.0
	
	punkt_param = PunktParameters()
	# if any customized abbrev
	#punkt_param.abbrev_types = set(['dr', 'vs', 'mr', 'mrs', 'prof', 'inc'])
	
	# tokenize to sentence	
	sentence_splitter = PunktSentenceTokenizer(punkt_param)
	sentences = sentence_splitter.tokenize(document.replace('\'s','_s'))
	
	# tokenize sentence to words	
	word_tokens=[[w.strip() for w in nltk.word_tokenize(s) if not w.strip().lower() in stopwords] for s in sentences]

	# extend token to bigram and trigram
	extended_tokens=[]
	for token_list in word_tokens:
		extended_tokens.append(token_list+nltk.bigrams(token_list)+nltk.trigrams(token_list))
		
	# word stemmer to normalize
	p_stemmer = PorterStemmer()
	stem_tokens=[]
	for token_list in word_tokens:
		stem_tokens.append([p_stemmer.stem(w) for w in token_list])
			
	# POS tags
	tags=[tagger.tag(a) for a in extended_tokens]
	
	tags_of_verbs=['NN','VB','VBP','VBG']
	tags_of_interest=['JJ','JJR','JJS','NN','NNP','NNPS','NNS','RB','RBR','RBS']
	tags_of_noun=['NN']
	merged_tags_uni = [word for sublist in tags for (word,tag) in sublist if tag in tags_of_verbs and isinstance(word,tuple)==False]
	merged_tags_bi = [word for sublist in tags for (word,tag) in sublist if tag in tags_of_interest and isinstance(word,tuple) and len(word)==2]
	merged_tags_tri = [word for sublist in tags for (word,tag) in sublist if tag in tags_of_interest and isinstance(word,tuple) and len(word)==3]

	uni_tags_fd=nltk.FreqDist(merged_tags_uni)
	bi_tags_fd=nltk.FreqDist(merged_tags_bi)
	tri_tags_fd=nltk.FreqDist(merged_tags_tri)

	return {'uni_fd':uni_tags_fd.max(),
			'bi_fd':bi_tags_fd.max(),
			'tri_fd':tri_tags_fd.max(), 
			}
	
def myRssParser(source,tagger):
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
		source_timestamp=i['updated_parsed']
		
		text_content=''
		
		# get linked content
		try:
			conn=urllib2.urlopen(i['id'])
			page=conn.read()
			conn.close()
		except: continue
		
		# clean up html		
		data=clean_html(page)
		tree=html.fromstring(data)
		if 'Reuters' in source.name:
			text_content=' '.join([j.text_content() for j in tree.cssselect('span#articleText p')])		

		# nltk analysis
		fd=myNLTKParser(text_content,tagger)
				
		# data
		content.append({'headline':title, 'link':detail_link, 'text':text_content, 'nltk':fd, 'source_timestamp':source_timestamp})
	
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
