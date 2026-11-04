"""Parse the reveal.js deck into structured slide data (slides.json).

Adapted from Pick-Your-Poison/tools/pptx-build/extract.py. Additions for this
deck: the active agenda item, <pre> code blocks, images (with alt text),
two-column layouts, hyperlinks, and line breaks inside table cells.
"""
import html, json, re, sys
from html.parser import HTMLParser
from pathlib import Path

WS = re.compile(r'\s+')
ROOT = Path(__file__).resolve().parents[2]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'index.html'
OUT = Path(__file__).resolve().parent / 'slides.json'


class Deck(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.slides = []
        self.cur = None
        self.stack = []            # open tag names
        self.buf = []              # runs for the current text block
        self.fmt = {'b': 0, 'i': 0, 'c': 0}
        self.href = None
        self.in_notes = False
        self.notes = []
        self.in_pre = False
        self.pre = []
        self.row = None
        self.col = None            # 0 or 1 inside <div class="col">, else None
        self.col_count = 0
        self.li_active = False

    # ------------------------------------------------------------ helpers
    def run(self, text):
        return {'t': text, 'b': self.fmt['b'] > 0, 'i': self.fmt['i'] > 0,
                'c': self.fmt['c'] > 0, 'href': self.href}

    def norm_runs(self):
        runs, self.buf = self.buf, []
        # collapse whitespace, merging spaces that straddle run boundaries
        out = []
        for r in runs:
            t = r['t'] if r['t'] == '\n' else WS.sub(' ', r['t'])
            if out and (out[-1]['t'].endswith((' ', '\n'))) and t.startswith(' '):
                t = t.lstrip(' ')
            if not t:
                continue
            key = (r['b'], r['i'], r['c'], r['href'])
            if out and (out[-1]['b'], out[-1]['i'], out[-1]['c'], out[-1]['href']) == key:
                out[-1] = dict(out[-1], t=out[-1]['t'] + t)
            else:
                out.append(dict(r, t=t))
        while out and not out[0]['t'].strip():
            out.pop(0)
        while out and not out[-1]['t'].strip():
            out.pop()
        if out:
            out[0] = dict(out[0], t=out[0]['t'].lstrip())
            out[-1] = dict(out[-1], t=out[-1]['t'].rstrip())
        return out

    def add_block(self, block):
        if self.col is not None:
            block['col'] = self.col
        self.cur['blocks'].append(block)

    def flush(self, kind, **extra):
        runs = self.norm_runs()
        if runs and ''.join(r['t'] for r in runs).strip():
            self.add_block({'kind': kind, 'runs': runs, **extra})

    # ------------------------------------------------------------ parser
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get('class') or ''
        if tag == 'section':
            self.cur = {'bg': a.get('data-background-image'), 'title': None,
                        'subtitle': None, 'blocks': [], 'notes': '', 'imgs': []}
            self.slides.append(self.cur)
            self.col_count = 0
            return
        if self.cur is None:
            return
        if tag == 'aside' and 'notes' in cls:
            self.in_notes, self.notes = True, []
            return
        if self.in_notes:
            return
        if tag == 'pre':
            self.in_pre, self.pre = True, []
        elif tag == 'br':
            if self.buf:
                self.buf.append(self.run('\n'))
            return
        elif tag == 'img':
            self.cur['imgs'].append({'src': a.get('src'), 'alt': a.get('alt') or '',
                                     'height': a.get('height'), 'col': self.col})
            return
        elif tag == 'div' and re.search(r'\bcol\b', cls):
            self.col = self.col_count
            self.col_count += 1
        elif tag in ('strong', 'b'):
            self.fmt['b'] += 1
        elif tag in ('em', 'i'):
            self.fmt['i'] += 1
        elif tag == 'code':
            self.fmt['c'] += 1
        elif tag == 'a':
            self.href = a.get('href')
        elif tag == 'tr':
            self.row = []
        elif tag in ('td', 'th'):
            self.buf = []
        elif tag in ('h2', 'h3', 'p', 'li'):
            self.buf = []
            self.li_active = tag == 'li' and 'active' in cls
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag == 'section':
            self.cur = None
            self.stack.clear()
            return
        if self.cur is None:
            return
        if tag == 'aside' and self.in_notes:
            # keep paragraph breaks: blank lines in the source separate thoughts
            text = ''.join(self.notes)
            paras = [' '.join(p.split()) for p in re.split(r'\n\s*\n', text)]
            self.cur['notes'] = '\n\n'.join(p for p in paras if p)
            self.in_notes = False
            return
        if self.in_notes:
            return
        if tag == 'pre':
            code = html.unescape(''.join(self.pre)).strip('\n')
            lines = code.split('\n')
            indent = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
            self.add_block({'kind': 'code', 'text': '\n'.join(l[indent:].rstrip() for l in lines)})
            self.in_pre = False
        elif tag in ('strong', 'b'):
            self.fmt['b'] = max(0, self.fmt['b'] - 1)
        elif tag in ('em', 'i'):
            self.fmt['i'] = max(0, self.fmt['i'] - 1)
        elif tag == 'code':
            self.fmt['c'] = max(0, self.fmt['c'] - 1)
        elif tag == 'a':
            self.href = None
        elif tag == 'div' and self.col is not None and self.stack and self.stack[-1] == 'div':
            self.col = None
        elif tag == 'h2':
            self.cur['title'] = ''.join(r['t'] for r in self.norm_runs())
        elif tag == 'h3':
            t = ''.join(r['t'] for r in self.norm_runs())
            if self.cur['title'] is None:
                self.cur['title'] = t
            else:
                self.cur['subtitle'] = t
        elif tag == 'p':
            self.flush('p')
        elif tag == 'li':
            parent = next((t for t in reversed(self.stack[:-1]) if t in ('ol', 'ul')), 'ul')
            self.flush('num' if parent == 'ol' else 'bullet', active=self.li_active)
        elif tag in ('td', 'th'):
            runs = self.norm_runs()
            if self.row is not None:
                self.row.append({'runs': runs, 'th': tag == 'th'})
        elif tag == 'tr':
            if self.row:
                self.add_block({'kind': 'row', 'cells': self.row})
            self.row = None
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_data(self, data):
        if self.in_notes:
            self.notes.append(data)
            return
        if self.cur is None:
            return
        if self.in_pre:
            self.pre.append(data)
            return
        if not self.stack:
            return
        data = WS.sub(' ', data)          # source indentation is not content
        if not data or (not self.buf and data == ' '):
            return
        self.buf.append(self.run(data))


deck = Deck()
deck.feed(SRC.read_text())

# merge consecutive rows into table blocks
for s in deck.slides:
    out, tbl = [], None
    for b in s['blocks']:
        if b['kind'] == 'row':
            if tbl is None:
                tbl = {'kind': 'table', 'rows': []}
                if 'col' in b:
                    tbl['col'] = b['col']
            tbl['rows'].append(b['cells'])
        else:
            if tbl:
                out.append(tbl)
                tbl = None
            out.append(b)
    if tbl:
        out.append(tbl)
    s['blocks'] = out

OUT.write_text(json.dumps(deck.slides, indent=1))

print(f"{len(deck.slides)} slides from {SRC}\n")
for i, s in enumerate(deck.slides, 1):
    kinds = {}
    for b in s['blocks']:
        kinds[b['kind']] = kinds.get(b['kind'], 0) + 1
    extra = []
    if s['imgs']:
        extra.append(f"{len(s['imgs'])} img")
    if any('col' in b for b in s['blocks']):
        extra.append('cols')
    if s['notes']:
        extra.append('notes')
    print(f"{i:>2} {str(s['title'])[:44]:<46} {str(kinds):<44} {' '.join(extra)}")
