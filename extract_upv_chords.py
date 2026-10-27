#!/usr/bin/env python3
"""Extract UPV chord/lyric table cells and build the verified local overlay.

This script is intentionally read-only against the UPV site and the song data.
It writes only upv_aligned.js and upv_alignment_report.json in this directory.
"""
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX_URL = 'https://tuna.upv.es/cancionero'
BASE_URL = 'https://tuna.upv.es/canciones/acordeswhite/'
MANIFEST = json.loads((ROOT / 'upv_alignment_manifest.json').read_text(encoding='utf-8'))

# UPV ids whose title and lyric match one current song after whitespace/case
# normalization. Mapping also records which current version has the same chord
# sequence, as verified in the source comparison. All other matched chord
# sequences are preserved as a separate UPV option.
SAME = {
    'A0026': ('Adiós a la llanera', 'Versión 1'), 'A0030': ('Adiós con el corazón', 'original'),
    'A0031': ('Amarraditos', 'Versión 1'), 'A0033': ('Angelitos negros', 'Versión 1'),
    'A0048': ('Asturias', 'original'), 'C0031': ('Cántame un pasodoble español', 'Versión 1'),
    'D0019': ('De colores', 'Versión 1'), 'M0052': ('El muerto vivo', 'Versión 1'),
    'P0033': ('El parrandero', 'Versión 1'), 'R0028': ('El rey', 'Versión 1'),
    'E0018': ('Estrella de la noche', 'original'), 'G0004': ('Gibraltareña', 'original'),
    'I0004': ('Islas Canarias', 'Versión 1'), 'B0025': ('La barca', 'Versión 1'),
    'M0033': ('La media vuelta', 'Versión 1'), 'S0009': ('La sirena', 'Versión 1'),
    'V0005': ('La viajerita', 'original'), 'M0048': ('Mira que eres linda', 'Versión 1'),
    'M0020': ('Moliendo café', 'Versión 1'), 'N0006': ('Noche de ronda', 'Versión 1'),
    'N0016': ('Noches de leyenda/Murcia', 'original'), 'O0006': ('Obsesión', 'original'),
    'P0048': ('Por la calle de Alcalá', 'original'), 'P0034': ('Porompompero', 'original'),
    'R0027': ('Rosa de Cuba', 'original'),
}
NEW_IDS = set(MANIFEST['newVersions'])
NEW_TITLES = {
    'A0029': 'A mi palomita', 'A0019': 'Así es mi Granada',
    'B0026': 'Bendita mi tierra guanche', 'J0001': 'Jamás, Jamás',
    'B0017': 'La banda', 'T0019': 'La tuna pasa', 'Y0005': 'Yolanda',
}

class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.table, self.row, self.cell = [], None, None, None
    def handle_starttag(self, tag, attrs):
        if tag == 'table': self.table = []
        elif tag == 'tr' and self.table is not None: self.row = []
        elif tag in ('td', 'th') and self.row is not None: self.cell = []
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_entityref(self, name):
        if self.cell is not None: self.cell.append(html.unescape('&' + name + ';'))
    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(''.join(self.cell)); self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.table.append(self.row); self.row = None
        elif tag == 'table' and self.table is not None:
            self.tables.append(self.table); self.table = None

class Links(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.links=[]; self.href=None; self.text=[]
    def handle_starttag(self, tag, attrs):
        if tag == 'a': self.href = dict(attrs).get('href'); self.text=[]
    def handle_data(self, data):
        if self.href is not None: self.text.append(data)
    def handle_endtag(self, tag):
        if tag == 'a' and self.href is not None:
            self.links.append((self.href, ''.join(self.text).strip())); self.href=None

def get(url, encoding='utf-8'):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36',
        'Referer': INDEX_URL,
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode(encoding, errors='replace')

def norm(text): return re.sub(r'\s+', '', text).casefold()
def strip_markup(text): return re.sub(r'<[^>]*>', '', html.unescape(text))

page = get(INDEX_URL, 'cp1252')
links = Links(); links.feed(page)
ids = {}
for href, title in links.links:
    match = re.search(r'/cancion/acordes/([A-Z]\d+)\.htm', href, re.I)
    if match: ids[match.group(1).upper()] = title
for sid in list(ids):
    match = re.search(r'([^<>]*?)\s*-\s*<a\s+HREF=[\"\'][^\"\']*prescancion\.asp\?Id_Cancion=' +
        re.escape(sid) + r'[\"\']', page, re.I)
    if match:
        source_title = html.unescape(match.group(1)).strip(' -\t\r\n')
        if source_title: ids[sid] = source_title

source = (ROOT / 'index.html').read_text(encoding='utf-8')
marker = 'const SONGS = '
start = source.index(marker) + len(marker)
songs, _ = json.JSONDecoder().raw_decode(source[start:])
by_title = {}
for song in songs: by_title.setdefault(norm(song['t']), []).append(song)

overlay, report = {}, {'indexLinks': len(ids), 'eligible': [], 'review': [], 'noChordPage': [], 'errors': []}
ordered_ids = sorted(ids)
with ThreadPoolExecutor(max_workers=12) as pool:
    source_pages = dict(zip(ordered_ids, pool.map(lambda sid: get(BASE_URL + sid + '.htm'), ordered_ids)))
for sid in ordered_ids:
    title = ids[sid]
    raw = source_pages[sid]
    parser = Tables(); parser.feed(raw)
    rows = []
    for table in parser.tables:
        if len(table) < 2: continue
        chords, lyrics = table[0], table[1]
        if len(chords) != len(lyrics):
            report['errors'].append({'id': sid, 'reason': 'Filas de tabla con distinto número de celdas'}); continue
        rows.append([[strip_markup(c), strip_markup(t)] for c, t in zip(chords, lyrics)])
    source_lyric = ''.join(cell[1] for table in rows for cell in table)
    if not rows:
        report['noChordPage'].append({'id': sid, 'title': title or 'Cielito Lindo'})
        continue

    target_title = SAME.get(sid, (None, None))[0] or NEW_TITLES.get(sid) or title
    candidates = by_title.get(norm(target_title or title), [])
    if len(candidates) != 1:
        report['review'].append({'id': sid, 'sourceTitle': title,
            'reason': 'Sin correspondencia única por título normalizado.'}); continue
    song = candidates[0]
    if norm(source_lyric) != norm(song.get('y','')):
        report['review'].append({'id': sid, 'sourceTitle': title, 'projectTitle': song['t'],
            'reason': 'El texto de letra difiere; requiere comparación manual.'}); continue
    if sid not in SAME and sid not in NEW_IDS:
        report['review'].append({'id': sid, 'sourceTitle': title, 'projectTitle': song['t'],
            'reason': 'Letra coincidente, pero secuencia de acordes aún no clasificada.'}); continue
    is_new = sid in NEW_IDS
    overlay[song['t']] = {'id': sid, 'mode': 'new' if is_new else 'align',
        'label': 'Versión UPV' if is_new else SAME[sid][1], 'rows': rows,
        'sourceTitle': target_title or title, 'note': MANIFEST['newVersions'].get(sid, '')}
    report['eligible'].append({'id': sid, 'sourceTitle': target_title or title, 'projectTitle': song['t'],
        'mode': 'new UPV version' if is_new else 'alignment for existing chord version',
        'tables': len(rows), 'rowCells': sum(len(table) for table in rows),
        'chords': sum(1 for table in rows for chord, _ in table if chord.strip())})

if len(report['eligible']) != 32:
    print('Review:', json.dumps(report['review'][:5], ensure_ascii=False))
    print('Errors:', json.dumps(report['errors'], ensure_ascii=False))
    raise SystemExit(f"Safety stop: expected 32 verified songs, got {len(report['eligible'])}; outputs not written")
report['counts'] = {'chordPages': len(ids) - len(report['noChordPage']),
    'titleAndLyricVerified': len(report['eligible']),
    'titleMatchLyricDiffers': sum(1 for row in report['review'] if row.get('reason','').startswith('El texto')),
    'titleNoUniqueMatch': sum(1 for row in report['review'] if row.get('reason','').startswith('Sin correspondencia')),
    'titleAndLyricButChordSequenceUnclassified': sum(1 for row in report['review'] if row.get('reason','').startswith('Letra coincidente')),
    'sameChordSequence': len(SAME), 'newChordVersions': len(NEW_IDS),
    'noChordTranscription': len(report['noChordPage'])}
js = '/* Generated from verified UPV table cells by extract_upv_chords.py */\nconst UPV_ALIGNED = ' + json.dumps(overlay, ensure_ascii=False, separators=(',', ':')) + ';\n'
(ROOT / 'upv_aligned.js').write_text(js, encoding='utf-8')
(ROOT / 'upv_alignment_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(f"Generated verified alignment for {len(report['eligible'])} songs; {len(report['review'])} require review; {len(report['errors'])} table errors.")
