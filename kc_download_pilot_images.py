from pathlib import Path
import requests

OUT=Path('pilot_images'); OUT.mkdir(exist_ok=True)
PRODUCTS={
 '148864048':('https://194939.x.yupoo.com/albums/148864048?uid=1',[
  'https://photo.yupoo.com/194939/e75c5c56/23fe5156.jpeg',
  'https://photo.yupoo.com/194939/898355df/954e0089.jpg',
  'https://photo.yupoo.com/194939/74e1ed28/0469f91f.jpg']),
 '130388579':('https://194939.x.yupoo.com/albums/130388579?uid=1',[
  'https://photo.yupoo.com/194939/e3d3f408/eca3134b.jpeg',
  'https://photo.yupoo.com/194939/d8e62f8c/04b442fc.jpeg']),
 '156434404':('https://194939.x.yupoo.com/albums/156434404?uid=1',[
  'https://photo.yupoo.com/194939/2780cbf6/c794dcd3.jpeg',
  'https://photo.yupoo.com/194939/8e44743d/d5fe3fa1.jpeg'])
}
HEAD={'User-Agent':'Mozilla/5.0'}
for album,(ref,urls) in PRODUCTS.items():
 d=OUT/album; d.mkdir(exist_ok=True)
 for i,url in enumerate(urls,1):
  r=requests.get(url,headers={**HEAD,'Referer':ref},timeout=45)
  print(album,i,r.status_code,r.headers.get('content-type'),len(r.content))
  r.raise_for_status()
  ct=(r.headers.get('content-type') or '').lower()
  if 'image' not in ct: raise RuntimeError(f'not image: {url} {ct}')
  ext='.jpg' if ('jpeg' in ct or 'jpg' in ct) else '.png'
  (d/f'{i:02d}{ext}').write_bytes(r.content)
