#!/opt/homebrew/bin/python3
import json, os, sys, time
args=sys.argv[1:]
allowed=bool(args and args[0]=='api')
if allowed:
    if 'graphql' in args:
        allowed=any(v.startswith('query=query(') for v in args) and not any(v.startswith('query=mutation') for v in args)
    else:
        for flag in ('-X','--method'):
            if flag in args and args[args.index(flag)+1]!='GET': allowed=False
        if ('-f' in args or '-F' in args) and '-X' not in args: allowed=False
with open(os.environ['CLAIM_API_LOG'],'a') as f:
    f.write(json.dumps({'time':time.time(),'argv':args,'read_allowed':allowed})+'\n')
if not allowed:
    sys.stderr.write('Live validation refused a non-read forge call\n')
    sys.exit(95)
os.execv('/opt/homebrew/bin/gh',['gh']+args)
