from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict
from pathlib import Path

import scrape_yupoo as base
import scrape_yupoo_v2 as v2

OUT = Path('out')
OUT.mkdir(exist_ok=True)
PREVIOUS = Path('previous/catalog.json')


def main():
    started = time.time()
    if not PREVIOUS.exists():
        raise SystemExit(f'Missing prior verified gallery catalog: {PREVIOUS}')

    previous_list = json.loads(PREVIOUS.read_text(encoding='utf-8'))
    previous = {str(x['album_id']): x for x in previous_list}
    print(f'Loaded {len(previous)} previously verified product galleries')

    categories = base.discover_categories()
    print(f'Selected categories: {len(categories)}')

    all_albums = {}
    membership = {}
    per_category_counts = {}
    for c in categories:
        albums = v2.scrape_category(c)
        per_category_counts[c['name']] = len(albums)
        for a in albums:
            membership.setdefault(a.album_id, set()).add(a.category_name)
            old = all_albums.get(a.album_id)
            if old is None or len(a.category_name) < len(old.category_name):
                all_albums[a.album_id] = a

    accepted, excluded = [], []
    for a in all_albums.values():
        if __import__('re').search(r'\bpet\b', a.source_title, __import__('re').I):
            excluded.append(asdict(a))
            continue
        x = base.classify(a)
        if not x:
            excluded.append(asdict(a))
            continue
        x['source_categories'] = sorted(membership.get(a.album_id, {a.category_name}))
        if x['kind'] == 'Unresolved':
            v2.apply_alias(x)
        accepted.append(x)

    inferred = {}
    junk = {'', 'album', '1', 'ac', 'aaa', 'nike', 'nike 90'}
    for x in accepted:
        if x['kind'] != 'Unresolved' or x['category_name'] not in v2.SPECIFIC_CONTEXT:
            continue
        cand = v2.candidate(x['source_title'])
        k = v2.key(cand)
        if not k or k in junk or k.isdigit():
            continue
        country, league = v2.SPECIFIC_CONTEXT[x['category_name']]
        team = v2.professional_name(cand)
        x.update(team=team, country=country, league=league, kind='Club', resolution='league-category')
        inferred.setdefault(k, (team, country, league))

    for x in accepted:
        if x['kind'] != 'Unresolved':
            continue
        cand = v2.candidate(x['source_title'])
        k = v2.key(cand)
        if k in inferred:
            t, c, l = inferred[k]
            x.update(team=t, country=c, league=l, kind='Club', resolution='cross-category')
        else:
            v2.apply_alias(x)

    reused = 0
    fetched = 0
    detailed = []
    for n, x in enumerate(accepted, 1):
        prior = previous.get(str(x['album_id']))
        if prior and prior.get('images') and not prior.get('detail_error'):
            for field in ('images', 'source_sizes', 'source_image_count_detected'):
                if field in prior:
                    x[field] = prior[field]
            x['detail_error'] = None
            reused += 1
        else:
            x = base.extract_images(x)
            fetched += 1
        v2.rebuild_copy(x)
        detailed.append(x)
        if n % 1000 == 0 or n == len(accepted):
            print(f'GALLERY {n}/{len(accepted)} reused={reused} fetched={fetched}')

    detailed.sort(key=lambda x: (x['country'], x['league'], x['team'], x['title'], x['album_id']))
    unresolved = [x for x in detailed if x['kind'] == 'Unresolved']
    no_images = [x for x in detailed if not x.get('images')]
    detail_errors = [x for x in detailed if x.get('detail_error')]

    collections = {
        'countries': sorted({x['country'] for x in detailed if x['country'] and x['kind'] != 'Unresolved'}),
        'leagues': sorted({(x['country'], x['league']) for x in detailed if x['league'] and x['kind'] != 'Unresolved'}),
        'teams': sorted({(x['country'], x['league'], x['team']) for x in detailed if x['team'] and x['kind'] != 'Unresolved'}),
    }
    collections['leagues'] = [{'country': a, 'league': b} for a, b in collections['leagues']]
    collections['teams'] = [{'country': a, 'league': b, 'team': c} for a, b, c in collections['teams']]

    summary = {
        'source': base.BASE,
        'selected_categories': categories,
        'per_category_album_counts': per_category_counts,
        'unique_albums_in_selected_categories': len(all_albums),
        'accepted_football_shirt_products': len(detailed),
        'excluded_non_shirts': len(excluded),
        'unresolved_team_classifications': len(unresolved),
        'products_without_images': len(no_images),
        'detail_fetch_errors': len(detail_errors),
        'reused_verified_galleries': reused,
        'new_gallery_fetches': fetched,
        'countries': len(collections['countries']),
        'leagues': len(collections['leagues']),
        'teams': len(collections['teams']),
        'elapsed_seconds': round(time.time() - started, 2),
        'qa_images_pass': len(no_images) == 0 and len(detail_errors) == 0,
    }

    (OUT / 'catalog.json').write_text(json.dumps(detailed, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'excluded.json').write_text(json.dumps(excluded, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'unresolved.json').write_text(json.dumps(unresolved, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'no_images.json').write_text(json.dumps(no_images, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'collections.json').write_text(json.dumps(collections, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    with (OUT / 'catalog.csv').open('w', encoding='utf-8-sig', newline='') as f:
        fields = ['album_id','title','team','country','league','category_name','source_title','source_url','kind','year','design','image_count_source_detected']
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for x in detailed:
            w.writerow({k: x.get(k, '') for k in fields})

    print('SUMMARY', json.dumps(summary, ensure_ascii=False))
    if unresolved:
        print('QA_WARN unresolved classifications', len(unresolved))
    if no_images:
        print('QA_FAIL products without images', len(no_images))
    if detail_errors:
        print('QA_FAIL detail fetch errors', len(detail_errors))


if __name__ == '__main__':
    main()
