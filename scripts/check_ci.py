"""Allow installation only after this exact revision has passed the complete CI."""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY='kkpo-adil/healthberg'


def successful_run(payload, revision):
    matching=[r for r in payload.get('workflow_runs',[]) if r.get('head_sha')==revision
              and r.get('path')=='.github/workflows/ci.yml' and r.get('name')=='Ajour checks'
              and r.get('event')=='push']
    if not matching:
        raise ValueError('Les tests GitHub de cette révision ne sont pas encore disponibles.')
    latest=max(matching,key=lambda r:r['id'])
    if latest.get('status')!='completed' or latest.get('conclusion')!='success':
        raise ValueError('Tests GitHub encore en cours ou en échec : installation bloquée. '+latest.get('html_url',''))
    return latest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('revision');args=parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}',args.revision):parser.error('Révision Git invalide')
    query=urllib.parse.urlencode({'head_sha':args.revision,'event':'push','per_page':100})
    req=urllib.request.Request(f'https://api.github.com/repos/{REPOSITORY}/actions/runs?{query}',
        headers={'Accept':'application/vnd.github+json','User-Agent':'Ajour-CI-check'})
    try:
        with urllib.request.urlopen(req,timeout=25) as response:payload=json.load(response)
        run=successful_run(payload,args.revision)
    except (OSError,ValueError,urllib.error.URLError) as exc:
        print('Installation non autorisée : '+str(exc),file=sys.stderr);return 2
    print('Tests GitHub validés pour '+args.revision[:12]+' : '+run['html_url'])
    return 0


if __name__=='__main__':raise SystemExit(main())
