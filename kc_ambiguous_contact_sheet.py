from pathlib import Path
from io import BytesIO
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

ITEMS = [{'label': 'Brazil | Arago',
  'album_id': '138123062',
  'source_url': 'https://194939.x.yupoo.com/albums/138123062?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/f89685f2/d9c07cc6.jpg',
  'source_title': 'Arago WOMAN'},
 {'label': 'Brazil | Atletico',
  'album_id': '200890466',
  'source_url': 'https://194939.x.yupoo.com/albums/200890466?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/fac4ce0e/5e15ab9b.jpeg',
  'source_title': 'Atletico woman 908'},
 {'label': 'Brazil | Dongda',
  'album_id': '189167275',
  'source_url': 'https://194939.x.yupoo.com/albums/189167275?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/b7f66b5c/176eaacb.jpeg',
  'source_title': 'Dongda 4XL 908'},
 {'label': 'England | Almirant Brown',
  'album_id': '183604330',
  'source_url': 'https://194939.x.yupoo.com/albums/183604330?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/a8699613/cad77819.jpeg',
  'source_title': 'Almirant Brown'},
 {'label': 'England | Derbyshire',
  'album_id': '169558123',
  'source_url': 'https://194939.x.yupoo.com/albums/169558123?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/689e4f67/6745c5ce.jpeg',
  'source_title': 'Derbyshire'},
 {'label': 'England | Lang Si',
  'album_id': '138406559',
  'source_url': 'https://194939.x.yupoo.com/albums/138406559?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/b329a74a/994e5c9a.jpg',
  'source_title': 'Lang Si2756556488'},
 {'label': 'England | Richmond',
  'album_id': '133917921',
  'source_url': 'https://194939.x.yupoo.com/albums/133917921?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/ffeb0dd2/c7e47238.jpg',
  'source_title': 'Richmond 403 810'},
 {'label': 'England | Sheffield',
  'album_id': '139131212',
  'source_url': 'https://194939.x.yupoo.com/albums/139131212?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/d46a32c1/179dfffb.jpg',
  'source_title': 'Sheffield'},
 {'label': 'France | Paris Kit',
  'album_id': '242237135',
  'source_url': 'https://194939.x.yupoo.com/albums/242237135?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/73dde5b66d/5fff1d94.jpeg',
  'source_title': 'Paris KIT'},
 {'label': 'France | Versailles',
  'album_id': '179518175',
  'source_url': 'https://194939.x.yupoo.com/albums/179518175?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/a9857f35/46662f6b.jpeg',
  'source_title': 'Versailles'},
 {'label': 'Germany | Berlin',
  'album_id': '173384721',
  'source_url': 'https://194939.x.yupoo.com/albums/173384721?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/cfcf2413/c3a03f69.jpeg',
  'source_title': 'Berlin 417'},
 {'label': 'Germany | Munich',
  'album_id': '207174767',
  'source_url': 'https://194939.x.yupoo.com/albums/207174767?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/b1ccae7a/9abcb20b.jpeg',
  'source_title': 'Munich 4XL'},
 {'label': 'Italy | AC A',
  'album_id': '228236557',
  'source_url': 'https://194939.x.yupoo.com/albums/228236557?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/0f1ca65a/02159d08.jpg',
  'source_title': 'AC 4XL A'},
 {'label': 'Italy | Saint Etienne',
  'album_id': '177941223',
  'source_url': 'https://194939.x.yupoo.com/albums/177941223?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/5c06a0d5/210f3b3a.jpeg',
  'source_title': 'Saint Etienne'},
 {'label': 'Spain | Castellion',
  'album_id': '180126378',
  'source_url': 'https://194939.x.yupoo.com/albums/180126378?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/33540599/7cc53e25.jpeg',
  'source_title': 'Castellion'},
 {'label': 'Spain | Erkules',
  'album_id': '192814913',
  'source_url': 'https://194939.x.yupoo.com/albums/192814913?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/bc7bcb00/36402a81.jpeg',
  'source_title': 'Erkules'},
 {'label': 'Spain | Eval',
  'album_id': '243022194',
  'source_url': 'https://194939.x.yupoo.com/albums/243022194?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/160876053a/8cccff3d.jpeg',
  'source_title': 'Eval 4XL'},
 {'label': 'Spain | Gaddis',
  'album_id': '176871761',
  'source_url': 'https://194939.x.yupoo.com/albums/176871761?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/7e6bbf07/4fb98b95.jpeg',
  'source_title': 'Gaddis S-2XL'},
 {'label': 'Spain | Gadis',
  'album_id': '181938977',
  'source_url': 'https://194939.x.yupoo.com/albums/181938977?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/35d9b71d/f678e673.jpeg',
  'source_title': 'Gadis'},
 {'label': 'Spain | Lacoroni',
  'album_id': '183303209',
  'source_url': 'https://194939.x.yupoo.com/albums/183303209?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/44e04a40/150761fe.jpeg',
  'source_title': 'Lacoroni'},
 {'label': 'Spain | Pachuca',
  'album_id': '182698550',
  'source_url': 'https://194939.x.yupoo.com/albums/182698550?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/8e36452c/c93802f1.jpeg',
  'source_title': 'PACHUCA S-4XL 912 818 268'},
 {'label': 'Spain | Santander Athletic',
  'album_id': '177493289',
  'source_url': 'https://194939.x.yupoo.com/albums/177493289?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/646b91bc/ee9fb9b3.jpeg',
  'source_title': 'Santander Athletic'},
 {'label': 'Spain | Santander Sport',
  'album_id': '177316451',
  'source_url': 'https://194939.x.yupoo.com/albums/177316451?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/78ad3483/3bb3d9f5.jpeg',
  'source_title': 'Santander Sport S-2XL'},
 {'label': 'Spain | Spaniard',
  'album_id': '207995182',
  'source_url': 'https://194939.x.yupoo.com/albums/207995182?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/d7f7b2e5/0c8648a6.jpeg',
  'source_title': 'Spaniard'},
 {'label': 'Spain | Spanish',
  'album_id': '172999765',
  'source_url': 'https://194939.x.yupoo.com/albums/172999765?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/a490b5ff/4fc736b1.jpeg',
  'source_title': 'Spanish'},
 {'label': 'Spain | Velva',
  'album_id': '172999163',
  'source_url': 'https://194939.x.yupoo.com/albums/172999163?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/e3a68fb6/34435f03.jpeg',
  'source_title': 'Velva'},
 {'label': 'Spain | Xihong',
  'album_id': '174828108',
  'source_url': 'https://194939.x.yupoo.com/albums/174828108?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/b56dcf67/dc0707e2.jpeg',
  'source_title': 'Xihong S-2XL327260141 AAA'},
 {'label': 'Spain | Xihong Athletic',
  'album_id': '181872100',
  'source_url': 'https://194939.x.yupoo.com/albums/181872100?uid=1',
  'image_url': 'https://photo.yupoo.com/194939/9c9fc0d4/22b27486.jpeg',
  'source_title': 'Xihong Athletic'}]

OUT = Path('ambiguous_images')
OUT.mkdir(exist_ok=True)

def load_font(size):
    for p in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf']:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()

font = load_font(22)
small = load_font(17)
thumb_w, thumb_h = 360, 360
label_h = 92
cols = 4
rows = (len(ITEMS) + cols - 1) // cols
sheet = Image.new('RGB', (cols * thumb_w, rows * (thumb_h + label_h)), 'white')
draw = ImageDraw.Draw(sheet)

session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 KickCrateCatalogQA/1.0'})

for idx, item in enumerate(ITEMS):
    r = session.get(item['image_url'], headers={'Referer': item['source_url']}, timeout=45)
    r.raise_for_status()
    img = Image.open(BytesIO(r.content)).convert('RGB')
    fit = ImageOps.contain(img, (thumb_w - 16, thumb_h - 16))
    tile = Image.new('RGB', (thumb_w, thumb_h), 'white')
    x = (thumb_w - fit.width) // 2
    y = (thumb_h - fit.height) // 2
    tile.paste(fit, (x, y))
    c = idx % cols
    rr = idx // cols
    sx, sy = c * thumb_w, rr * (thumb_h + label_h)
    sheet.paste(tile, (sx, sy))
    label = f"{idx+1:02d} {item['label']}"
    source = f"{item['source_title']} | album {item['album_id']}"
    draw.text((sx+8, sy+thumb_h+5), label, fill='black', font=font)
    draw.text((sx+8, sy+thumb_h+38), source[:48], fill='black', font=small)
    (OUT / f"{idx+1:02d}-{item['album_id']}.jpg").write_bytes(r.content)

sheet.save(OUT / 'ambiguous-contact-sheet.jpg', quality=92)
print('saved', len(ITEMS), 'images and contact sheet')
