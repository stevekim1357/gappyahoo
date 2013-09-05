#!/usr/bin/env python
import optparse
#import jwt
import sys
import json
import time

__prog__ = 'jwt'
__version__ = '0.1'

def fix_optionparser_whitespace(input):
    """Hacks around whitespace Nazi-ism in OptionParser"""
    newline = ' ' * 80
    doublespace = '\033[8m.\033[0m' * 2
    return input.replace('  ', doublespace).replace('\n', newline)

def main():
    """Encodes or decodes JSON Web Tokens based on input
  
Decoding examples:
  
  %prog --key=secret json.web.token
  %prog --no-verify json.web.token
  
Encoding requires the key option and takes space separated key/value pairs 
separated by equals (=) as input. Examples:
  
  %prog --key=secret iss=me exp=1302049071
  %prog --key=secret foo=bar exp=+10
  
The exp key is special and can take an offset to current Unix time. 
"""
    p = optparse.OptionParser(description=fix_optionparser_whitespace(main.__doc__),
                                prog=__prog__,
                                version='%s %s' % (__prog__, __version__),
                                usage='%prog [options] input')
    p.add_option('-n', '--no-verify', action='store_false', dest='verify', default=True,
                    help='ignore signature verification on decode')
    p.add_option('--key', dest='key', metavar='KEY', default=None,
                    help='set the secret key to sign with')
    p.add_option('--alg', dest='algorithm', metavar='ALG', default='HS256',
                    help='set crypto algorithm to sign with. default=HS256')
    
    options, arguments = p.parse_args()
    if len(arguments) > 0 or not sys.stdin.isatty():
        # Try to decode
        try:
            if not sys.stdin.isatty():
                token = sys.stdin.read()
            else:
                token = arguments[0]
            valid_jwt = jwt.header(token)
            if valid_jwt:
                try:
                    print json.dumps(jwt.decode(token, key=options.key, verify=options.verify))
                    sys.exit(0)
                except jwt.DecodeError, e:
                    print e
                    sys.exit(1)
        except jwt.DecodeError:
            pass
        
        # Try to encode
        if options.key is None:
            print "Key is required when encoding. See --help for usage."
            sys.exit(1)
        
        # Build payload object to encode
        payload = {}
        for arg in arguments:
            try:
                k,v = arg.split('=', 1)
                # exp +offset special case?
                if k == 'exp' and v[0] == '+' and len(v) > 1:
                    v = str(int(time.time()+int(v[1:])))
                # Cast to integer?
                if v.isdigit():
                    v = int(v)
                else:
                    # Cast to float?
                    try:
                        v = float(v)
                    except ValueError:
                        pass
                # Cast to true, false, or null?
                constants = {'true': True, 'false': False, 'null': None}
                if v in constants:
                    v = constants[v]
                payload[k] = v
            except ValueError:
                print "Invalid encoding input at %s" % arg
                sys.exit(1)
        
        try:
            print jwt.encode(payload, key=options.key, algorithm=options.algorithm)
            sys.exit(0)
        except Exception, e:
            print e
            sys.exit(1)
    else:
        p.print_help()

if __name__ == '__main__':
     main()
