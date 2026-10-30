#!/usr/bin/env python3
"""Daily refresh of the 2027 Jacksonville races data (assets/races-data.js).

Pulls the Duval County Supervisor of Elections campaign finance listing
(VoterFocus, 2027 reporting group), then each candidate's itemized export,
and rewrites the CANDIDATES block. Hand-curated fields (display name, photo,
website, platform and its source) are kept. New filers are added; candidates
who are no longer active are dropped. Standard library only.

Exit code 0 always unless the source looks broken, so the workflow only
commits when the data file actually changed.
"""
import csv, html, io, json, re, sys, time, urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'assets' / 'races-data.js'
PHOTOS = ROOT / 'assets' / 'races'
BASE = 'https://www.voterfocus.com/CampaignFinance/'
LIST_URL = BASE + 'candidate_pr.php?c=duval&el=41&e=41'
PAGE_URL = BASE + 'candidate_pr.php?op=cv&e=41&c=duval&ca={ca}&rellevel=4&committee=N'
CSV_URL = BASE + 'export.php?op=CFINANCE&cand_id={ca}&dhc=0&county=duval'
UA = {'User-Agent': 'Mozilla/5.0 (tonystangent.com races page; daily public-records refresh)'}

CATS = [('refunds', r'refund'), ('filing/qualifying fees', r'filing|qualif'),
        ('digital/web', r'facebook|meta|digital|website|web site|\bweb\b|e-?mail|software|google|online|\btext|sms|social|domain|hosting|squarespace|wix|nationbuilder|video'),
        ('advertising/print/mail', r'advert|mail|print|postage|sign|banner|billboard|shirt|merch|card|hanger|radio|\btv\b|media|marketing|promot|\bads?\b|stamp|flyer|literature|magnet|button|\bhat'),
        ('consulting/compliance', r'consult|compliance|accounting|treasurer|strategy|management|cpa|legal|attorney|bookkeep|poll|research|survey'),
        ('staff/payroll', r'salary|payroll|contract labor|staff|canvass|wage|stipend'),
        ('events/meals', r'event|meal|food|cater|venue|ticket|entertain|reception|rental|party|fundrais|drink|restaurant'),
        ('bank/processing fees', r'fee|bank|charge|processing|merchant|transaction|stripe|anedot|winred|actblue'),
        ('supplies/office', r'suppl|office')]
TYPES = {'I': 'individuals', 'B': 'businesses', 'F': 'political committees', 'C': 'committees', 'P': 'party', 'S': 'self', 'O': 'other'}


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return r.read().decode('utf-8', 'ignore')
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(4 * (i + 1))


def money(s):
    return float(s.replace('$', '').replace(',', '').strip() or 0)


def parse_list(src):
    rows, office = [], None
    for part in re.split(r'(<div class="col-xs-12 officename">.*?</div>)', src, flags=re.S):
        m = re.match(r'<div class="col-xs-12 officename">Office:\s*(.*?)</div>', part, re.S)
        if m:
            office = html.unescape(m.group(1)).strip()
            continue
        for blk in re.findall(r'<div class="col-xs-12 detailrow candidate.*?</a>', part, re.S):
            ca = re.search(r'ca=(\d+)', blk).group(1)
            txt = [t.strip() for t in re.sub(r'<[^>]+>', '\n', blk).split('\n')]
            txt = [html.unescape(t) for t in txt if t and t not in ('status', 'monetary', 'in-kind', 'expenditures', 'Contributions', 'In-Kind', 'Expenditures')]
            name_party = txt[0]
            mp = re.match(r'(.*) \((\w+)\)$', name_party)
            status = ' '.join(t for t in txt[1:] if not t.startswith('$')).strip()
            amounts = [money(t) for t in txt if t.startswith('$')]
            rows.append(dict(ca=ca, seat=office, name=mp.group(1) if mp else name_party, party=mp.group(2) if mp else '',
                             status=status, raised=amounts[0] if amounts else 0.0, inkind=amounts[1] if len(amounts) > 1 else 0.0,
                             spent=amounts[2] if len(amounts) > 2 else 0.0))
    return rows


def category(desc, name):
    s = (desc + ' ' + name).lower()
    for c, p in CATS:
        if re.search(p, s):
            return c
    return 'other'


def itemized(ca):
    src = get(CSV_URL.format(ca=ca))
    if 'No records found' in src[:300]:
        return {}
    rows = list(csv.DictReader(io.StringIO(src)))
    deletes = [r for r in rows if r.get('Amend. code') == 'D']
    keep = []
    for r in rows:
        if r.get('Amend. code') == 'D':
            continue
        m = [d for d in deletes if d['name'] == r['name'] and d['amount'] == r['amount'] and d['Cont/Exp'] == r['Cont/Exp']]
        if m and r.get('Amend. code') != 'A':
            deletes.remove(m[0])
            continue
        keep.append(r)
    loans = selfm = 0.0
    types, cats, payees = Counter(), Counter(), Counter()
    for r in keep:
        a = float(r.get('amount') or 0)
        nm = re.sub(r'\s+', ' ', r.get('name', '')).strip()
        if r['Cont/Exp'] == 'C':
            if r.get('item type') == 'IK':
                continue
            if r.get('item type') == 'LO':
                loans += a
            t = TYPES.get(r.get('cont. type', ''), 'other')
            types[t] += a
            if t == 'self':
                selfm += a
        elif r['Cont/Exp'] in ('E', 'D'):
            cats[category((r.get('description') or '').replace('<br>', ' '), nm)] += a
            payees[nm] += a
    return dict(loans=round(loans, 2), self=round(selfm, 2),
                donors={k: round(v, 2) for k, v in types.most_common()},
                cats={k: round(v, 2) for k, v in cats.most_common() if v > 0},
                payees=[[k, round(v, 2)] for k, v in payees.most_common(3)])


def page_info(ca):
    src = get(PAGE_URL.format(ca=ca))
    names = re.findall(r'<span class="ReportPeriodName">([^<]+)</span>', src)
    asof = 'none filed'
    if names:
        last = names[-1].strip()
        period = ''
        m = re.findall(r'\((\d+/\d+/(\d{4})) - (\d+/\d+/\d{4})\)', src)
        if m:
            period = f' ({m[-1][0]} - {m[-1][2]})'
            asof = f'{last} {m[-1][1]}{period}'
        else:
            asof = last
    has_photo = f'photo_duval/cand_{ca}' in src
    return asof, has_photo


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def main():
    js = DATA.read_text(encoding='utf-8')
    m = re.search(r'\n CANDIDATES: (\[.*?\]),\n GEO: ', js, re.S)
    old = json.loads(m.group(1))
    old_by_ca = {c.get('ca'): c for c in old if c.get('ca')}

    rows = [r for r in parse_list(get(LIST_URL)) if re.search(r'Active-?\s*Filed', r['status'])]
    if len(rows) < max(10, len(old) // 2):
        sys.exit(f'Source returned only {len(rows)} active candidates (had {len(old)}); not updating.')

    new = []
    for r in rows:
        prev = old_by_ca.get(r['ca'], {})
        try:
            fin = itemized(r['ca'])
            asof, has_photo = page_info(r['ca'])
        except Exception as e:  # keep yesterday's numbers for this one candidate
            print('warn', r['ca'], e)
            if prev:
                new.append(prev)
            continue
        photo = prev.get('photo')
        if not photo and has_photo:
            fn = f"{slug(r['name'])}.jpg"
            try:
                req = urllib.request.Request(BASE + f"photo_duval/cand_{r['ca']}.jpg", headers=UA)
                with urllib.request.urlopen(req, timeout=40) as resp:
                    b = resp.read()
                if len(b) > 2000:
                    (PHOTOS / fn).write_bytes(b)
                    photo = f'assets/races/{fn}'
            except Exception as e:
                print('photo warn', r['ca'], e)
        new.append(dict(
            seat=r['seat'], name=prev.get('name') or r['name'], party=r['party'] or prev.get('party', ''),
            inc=prev.get('inc', 'no'), photo=photo, web=prev.get('web'),
            raised=round(r['raised'], 2), spent=round(r['spent'], 2), inkind=round(r['inkind'], 2),
            loans=fin.get('loans', 0), self=fin.get('self', 0), asof=asof, ca=r['ca'],
            cats=fin.get('cats', {}), donors=fin.get('donors', {}), payees=fin.get('payees', []),
            platform=prev.get('platform', []), psrc=prev.get('psrc')))
        time.sleep(0.5)

    def key(lst):
        return json.dumps(sorted(lst, key=lambda x: x.get('ca') or ''), sort_keys=True)

    if key(new) == key(old):
        print('No changes.')
        return

    added = sorted({c['ca'] for c in new} - set(old_by_ca))
    gone = sorted(set(old_by_ca) - {c['ca'] for c in new})
    for ca in added:
        c = next(x for x in new if x['ca'] == ca)
        print(f'NEW filer: {c["name"]} ({c["party"]}) for {c["seat"]}')
    for ca in gone:
        print(f'NO LONGER ACTIVE: {old_by_ca[ca]["name"]} ({old_by_ca[ca]["seat"]})')

    today = datetime.now(timezone(timedelta(hours=-4))).strftime('%b. %-d, %Y').replace('May.', 'May').replace('Jun.', 'June').replace('Jul.', 'July').replace('Sep.', 'Sept.')
    js = js[:m.start(1)] + json.dumps(new, ensure_ascii=False, separators=(',', ':')).replace('},{', '},\n{') + js[m.end(1):]
    js = re.sub(r'\n UPDATED: "[^"]*"', f'\n UPDATED: "Supervisor of Elections filings, refreshed {today}"', js, count=1)
    DATA.write_text(js, encoding='utf-8')
    print(f'Updated {len(new)} candidates ({len(added)} new, {len(gone)} removed).')


if __name__ == '__main__':
    main()
