from __future__ import annotations
import json, re
from pathlib import Path
from bs4 import BeautifulSoup
import scrape_yupoo as base
import scrape_yupoo_v2 as v2

items=json.loads(Path('visual_input/unresolved.json').read_text(encoding='utf-8'))
# inspect all weak-title albums so the result can be used programmatically if metadata is useful
weak={'Album','', '1','AC'}
out=[]
for n,x in enumerate([z for z in items if v2.candidate(z['source_title']) in weak],1):
    try:
        h=base.fetch(x['source_url'],attempts=4)
        soup=BeautifulSoup(h,'lxml')
        meta={}
        for m in soup.find_all('meta'):
            key=m.get('property') or m.get('name')
            val=m.get('content')
            if key and val and any(t in key.lower() for t in ('title','description','image')):
                meta[key]=val
        img_attrs=[]
        for img in soup.find_all('img')[:50]:
            d={k:img.get(k) for k in ('alt','title','data-title','data-description','data-origin-src','src') if img.get(k)}
            if d: img_attrs.append(d)
        # keep meaningful short text snippets while removing navigation boilerplate repeats
        texts=[]
        for tag in soup.find_all(['h1','h2','h3','p','figcaption','span','div']):
            t=' '.join(tag.get_text(' ',strip=True).split())
            if 2 <= len(t) <= 300 and t not in texts:
                texts.append(t)
            if len(texts)>=100: break
        out.append({'album_id':x['album_id'],'source_title':x['source_title'],'category_name':x['category_name'],'meta':meta,'img_attrs':img_attrs[:20],'texts':texts[:100]})
    except Exception as e:
        out.append({'album_id':x['album_id'],'source_title':x['source_title'],'category_name':x['category_name'],'error':str(e)})
    if n%25==0: print('META',n)
Path('metadata_qa.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print('DONE',len(out))
