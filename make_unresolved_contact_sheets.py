from __future__ import annotations

import json, re, io, math, time
from collections import Counter
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

SRC=Path('visual_input/unresolved.json')
OUT=Path('visual_qa'); OUT.mkdir(exist_ok=True)

NOISE=re.compile(r"\b(home|away|guest|third|3rd|fourth|4th|player|players|version|jersey|shirt|retro|kids?|women'?s?|woman|long[- ]sleeved?|goalkeeper|gk|fan|aaa|football|soccer)\b",re.I)
def candidate(raw):
    s=raw.strip()
    s=re.sub(r'\b(?:19|20)?\d{2}\s*[/\-]\s*(?:19|20)?\d{2}\b',' ',s)
    s=re.sub(r'\b(?:19|20)\d{2}\b',' ',s)
    s=re.sub(r'\b(?:0\d|1\d|2\d)(?:0\d|1\d|2\d)\b',' ',s)
    s=re.sub(r'\b(?:XS|S|M|L|XL|XXL|XXXL|XXXXL|[2-6]XL)\b',' ',s,flags=re.I)
    s=re.sub(r'\b[A-Z]\d{3,5}\b',' ',s,flags=re.I)
    s=re.sub(r'\b\d{3,4}\b',' ',s)
    s=re.sub(r'\b1\s*:\s*1\b',' ',s)
    s=NOISE.sub(' ',s)
    s=re.sub(r"[^A-Za-zÀ-ÿ0-9&.' -]+",' ',s)
    return re.sub(r'\s+',' ',s).strip(' -.')

items=json.loads(SRC.read_text(encoding='utf-8'))
counts=Counter(candidate(x['source_title']) for x in items)
visual_candidates={
    'Album','', '1','AC','OASIS','Nike 90','streetwear brand','CHEERS','Dula','Hartz','Nesa Bulls','Faye','Washington','Red Bull',
    'Campos',"King' Alliance",'California Independence','The Phoenix','Ucasa','Laconia','Corvado','Durra','Savaldo','Tefuvirahap','Nakasa','Chief Caesar','Cypress Sun God','Ahliatbala'
}
selected=[x for x in items if candidate(x['source_title']) in visual_candidates]
# Also one representative image for each other candidate occurring at least 3 times, useful for checking translations.
seen=set()
for x in items:
    c=candidate(x['source_title'])
    if c not in visual_candidates and counts[c]>=3 and c not in seen:
        y=dict(x); y['_representative']=True; selected.append(y); seen.add(c)

session=requests.Session(); session.headers.update({'User-Agent':'Mozilla/5.0 catalog-qa/1.0'})
font=ImageFont.load_default()
manifest=[]
TILE_W,TILE_H=360,420; IMG_H=320; COLS,ROWS=4,4; PER=COLS*ROWS

def load_img(url):
    try:
        r=session.get(url,timeout=20); r.raise_for_status()
        im=Image.open(io.BytesIO(r.content)).convert('RGB')
        im.thumbnail((TILE_W-16,IMG_H-8),Image.Resampling.LANCZOS)
        canvas=Image.new('RGB',(TILE_W-16,IMG_H-8),'white')
        canvas.paste(im,((canvas.width-im.width)//2,(canvas.height-im.height)//2))
        return canvas,None
    except Exception as e:
        return Image.new('RGB',(TILE_W-16,IMG_H-8),'white'),str(e)

for i,x in enumerate(selected):
    x['_candidate']=candidate(x['source_title'])
    x['_index']=i
    url=(x.get('images') or [x.get('thumbnail')])[0]
    im,err=load_img(url)
    x['_visual_error']=err
    x['_visual_file_image']=url
    x['_loaded_image']=im
    manifest.append({k:v for k,v in x.items() if not k.startswith('_loaded')})
    if (i+1)%50==0: print('downloaded',i+1,'/',len(selected))

for sheet_no,start in enumerate(range(0,len(selected),PER),1):
    batch=selected[start:start+PER]
    sheet=Image.new('RGB',(TILE_W*COLS,TILE_H*ROWS),'white')
    d=ImageDraw.Draw(sheet)
    for j,x in enumerate(batch):
        col=j%COLS; row=j//COLS; ox=col*TILE_W; oy=row*TILE_H
        sheet.paste(x['_loaded_image'],(ox+8,oy+8))
        label=f"#{x['_index']} | {x['album_id']} | {x['_candidate'] or '[blank]'}\n{x['category_name'][:38]}\n{x['source_title'][:46]}"
        d.multiline_text((ox+8,oy+IMG_H+7),label,fill='black',font=font,spacing=3)
        d.rectangle((ox,oy,ox+TILE_W-1,oy+TILE_H-1),outline='gray',width=1)
    path=OUT/f'sheet_{sheet_no:03d}.jpg'; sheet.save(path,quality=88,optimize=True)
    print('saved',path)

(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'summary.json').write_text(json.dumps({'unresolved_total':len(items),'visual_items':len(selected),'sheets':math.ceil(len(selected)/PER),'candidate_counts':counts.most_common()},ensure_ascii=False,indent=2),encoding='utf-8')
print('VISUAL_SUMMARY',len(selected),math.ceil(len(selected)/PER))
