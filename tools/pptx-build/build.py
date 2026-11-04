"""Build the Live! 360 Orlando 2026 PowerPoint deck from the reveal.js slides.

Adapted from Pick-Your-Poison/tools/pptx-build/build.py, which targeted the PASS
Summit template. This template is smaller (10 x 5.625 in), has only three sample
slides (title, session survey, blank content), and puts a Live! 360 logo in the
bottom-right corner of every content slide, so content keeps clear of it.

Usage:  python build.py [path/to/template.pptx]
"""
import io, json, math, sys
from pathlib import Path

from PIL import Image, ImageFilter
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls, qn
from pptx.util import Emu, Inches, Pt

HERE   = Path(__file__).resolve().parent
ROOT   = HERE.parents[1]
ASSETS = ROOT.parent / 'WebsiteAssets'
TPL    = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / 'Downloads' / 'L360OR26_Speaker Slide Template.pptx'
OUT    = ROOT / 'Microsoft-Foundry-for-the-Skeptical-Developer.pptx'
SLIDES = json.loads((HERE / 'slides.json').read_text())

TITLE     = 'Microsoft Foundry for the Skeptical Developer'
SPEAKER   = 'Kevin Feasel'
COMPANY   = 'Catallaxy Services'
LEVEL     = 'Level: Intermediate'

WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
INK       = RGBColor(0x1A, 0x1A, 0x1A)
TEAL      = RGBColor(0x2E, 0x7D, 0x7D)    # darkened Live! 360 logo teal (#60A6A6) for contrast
TEAL_TINT = RGBColor(0xEA, 0xF4, 0xF4)
CODE_BG   = RGBColor(0xF2, 0xF2, 0xF2)
SKY       = RGBColor(0x93, 0xCD, 0xDD)    # the title slide's speaker colour (accent5, 40% lighter)

# Geometry, in inches. The template's title placeholder spans 0.23 -> 1.17.
LEFT, WIDTH   = 0.5, 9.0
TOP, BOTTOM   = 1.30, 5.05
LOGO_X, LOGO_Y = 8.75, 4.55                # keep anything right of X out from below Y
GAP           = 0.15
SIZES         = (20, 18, 16, 14)
CHAR_EM       = 0.45                        # average Calibri glyph width, as a fraction of size


# ---------------------------------------------------------------- helpers
def ph_by_idx(slide, idx):
    for sh in slide.placeholders:
        if sh.placeholder_format.idx == idx:
            return sh
    return None


def drop(shape):
    shape._element.getparent().remove(shape._element)


def text_of(runs):
    return ''.join(r['t'] for r in runs)


def set_alt(pic, text):
    pic._element.nvPicPr.cNvPr.set('descr', text)


def para_format(p, kind, size):
    """Bullets and indents set explicitly, so a text box and the body
    placeholder render a block identically."""
    pPr = p._p.get_or_add_pPr()
    for tag in ('a:buNone', 'a:buChar', 'a:buAutoNum', 'a:buFont'):
        for e in pPr.findall(qn(tag)):
            pPr.remove(e)
    p.space_before = Pt(0)
    p.space_after = Pt(round(size * 0.45))
    if kind == 'bullet':
        pPr.set('marL', str(Inches(0.3)))
        pPr.set('indent', str(-Inches(0.3)))
        pPr.append(parse_xml(f'<a:buFont {nsdecls("a")} typeface="Arial"/>'))
        pPr.append(parse_xml(f'<a:buChar {nsdecls("a")} char="&#8226;"/>'))
    elif kind == 'num':
        pPr.set('marL', str(Inches(0.45)))
        pPr.set('indent', str(-Inches(0.45)))
        pPr.append(parse_xml(f'<a:buAutoNum {nsdecls("a")} type="arabicPeriod"/>'))
    else:
        pPr.set('marL', '0')
        pPr.set('indent', '0')
        pPr.append(parse_xml(f'<a:buNone {nsdecls("a")}/>'))


def add_runs(p, runs, size=None, color=None, bold=None):
    for r in runs:
        for k, seg in enumerate(r['t'].split('\n')):
            if k:
                p.add_line_break()
            if not seg:
                continue
            run = p.add_run()
            run.text = seg
            f = run.font
            if r.get('b') or bold:
                f.bold = True
            if r.get('i'):
                f.italic = True
            if r.get('c'):
                f.name = 'Courier New'
            if size:
                f.size = size
            if color is not None:
                f.color.rgb = color
            if r.get('href'):
                run.hyperlink.address = r['href']


def fill_text(tf, blocks, size, color=None):
    tf.word_wrap = True
    tf.auto_size = None
    for i, b in enumerate(blocks):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para_format(p, b['kind'], size)
        active = b.get('active')
        add_runs(p, b['runs'], size=Pt(size), color=(SKY if active else color),
                 bold=True if active else None)


def new_textbox(slide, x, y, w, h):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = Inches(0.1)
    tf.margin_top = tf.margin_bottom = Inches(0.05)
    return tb


# ---------------------------------------------------------------- measuring
def lines_for(text, size, width):
    per_line = max(1.0, width * 72 / (size * CHAR_EM))
    return sum(max(1, math.ceil(len(seg) / per_line)) for seg in text.split('\n'))


def text_height(blocks, size, width):
    h = 0.1
    for b in blocks:
        indent = {'bullet': 0.3, 'num': 0.45}.get(b['kind'], 0)
        n = lines_for(text_of(b['runs']), size, width - indent - 0.2)
        h += n * size * 1.2 / 72 + size * 0.45 / 72
    return h


def col_widths(rows, total):
    longest = [max(len(text_of(r[c]['runs'])) for r in rows) for c in range(len(rows[0]))]
    raw = [max(6, n) for n in longest]
    return [total * n / sum(raw) for n in raw]


def table_height(rows, size, total):
    widths = col_widths(rows, total)
    h = 0
    for row in rows:
        n = max(lines_for(text_of(c['runs']), size, w - 0.2) for c, w in zip(row, widths))
        h += n * size * 1.2 / 72 + 0.1
    return h


def code_size(text, width):
    """Largest size, 14pt down to 10pt, at which the longest line fits unwrapped."""
    longest = max(len(l) for l in text.split('\n'))
    fits = (width - 0.3) * 72 / (longest * 0.6)      # Courier New is 0.6 em wide
    return max(10, min(14, int(fits)))


def code_height(text, width):
    return len(text.split('\n')) * code_size(text, width) * 1.2 / 72 + 0.2


def table_size(size):
    return max(size - 4, 12)


# ---------------------------------------------------------------- building blocks
def add_table(slide, rows, x, y, w, size):
    cols = max(len(r) for r in rows)
    rows = [r + [{'runs': [], 'th': False}] * (cols - len(r)) for r in rows]
    widths = col_widths(rows, w)
    gf = slide.shapes.add_table(len(rows), cols, Inches(x), Inches(y), Inches(w),
                                Inches(table_height(rows, size, w)))
    tbl = gf.table
    for c, cw in enumerate(widths):
        tbl.columns[c].width = Inches(cw)
    header = all(c['th'] for c in rows[0])
    tbl.first_row = header
    for ri, row in enumerate(rows):
        is_head = header and ri == 0
        for ci, val in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            txt = text_of(val['runs'])
            # money and percentages read better right-aligned
            if not is_head and txt[:1] in '$<0123456789' and ci > 0:
                p.alignment = PP_ALIGN.RIGHT
            add_runs(p, val['runs'], size=Pt(size),
                     color=WHITE if is_head else INK, bold=True if is_head else None)
            cell.fill.solid()
            cell.fill.fore_color.rgb = TEAL if is_head else (WHITE if ri % 2 else TEAL_TINT)
    return gf


def add_code(slide, text, x, y, w):
    size = code_size(text, w)
    h = code_height(text, w)
    tb = new_textbox(slide, x, y, w, h)
    tb.fill.solid()
    tb.fill.fore_color.rgb = CODE_BG
    tf = tb.text_frame
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = Inches(0.15)
    tf.margin_top = tf.margin_bottom = Inches(0.08)
    for i, line in enumerate(text.split('\n')):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para_format(p, 'p', 0)
        p.space_after = Pt(0)
        r = p.add_run()
        r.text = line
        r.font.name = 'Courier New'
        r.font.size = Pt(size)
        r.font.color.rgb = INK
    return h


def set_background(slide, image_path):
    _, rId = slide.part.get_or_add_image_part(str(image_path))
    bg = parse_xml(
        f'<p:bg {nsdecls("p", "a", "r")}><p:bgPr>'
        f'<a:blipFill dpi="0" rotWithShape="1"><a:blip r:embed="{rId}"/><a:srcRect/>'
        f'<a:stretch><a:fillRect/></a:stretch></a:blipFill><a:effectLst/></p:bgPr></p:bg>')
    cSld = slide._element.cSld
    cSld.insert(0, bg)


def set_title(slide, text, color=None):
    title = slide.shapes.title
    title.text_frame.text = text
    size = 32 if len(text) <= 30 else 28 if len(text) <= 38 else 24
    for r in title.text_frame.paragraphs[0].runs:
        r.font.size = Pt(size)
        r.font.bold = True
        if color is not None:
            r.font.color.rgb = color
    return title


def fit_picture(slide, path, alt, box=(LEFT, TOP, WIDTH, BOTTOM - TOP)):
    """Largest centred fit inside `box` that stays clear of the logo corner."""
    w_px, h_px = Image.open(path).size
    ratio = w_px / h_px
    bx, by, bw, bh = box

    def fit(maxw, maxh):
        w = min(maxw, maxh * ratio)
        return w, w / ratio

    w, h = fit(bw, bh)
    if 5.0 + w / 2 > LOGO_X and by + h > LOGO_Y:
        a = fit(bw, LOGO_Y - by)                  # shorter, full width
        b = fit(2 * (LOGO_X - 5.0), bh)           # narrower, full height
        w, h = max(a, b, key=lambda s: s[0] * s[1])
    pic = slide.shapes.add_picture(str(path), Inches(5.0 - w / 2), Inches(by), Inches(w), Inches(h))
    set_alt(pic, alt)
    return pic


# ---------------------------------------------------------------- dark background
def dark_background(prs):
    """The title slide's gradient, cropped clear of its baked-in event logos."""
    out = HERE / 'dark-bg.jpg'
    title_slide = prs.slides[0]
    blob = next(rel.target_part.blob for rel in title_slide.part.rels.values()
                if 'image' in rel.reltype)
    im = Image.open(io.BytesIO(blob)).convert('RGB')
    w, h = im.size
    # Logos: the event badge top-left, the brand strip along the bottom. A crop of
    # equal width and height fractions keeps the 16:9 aspect ratio.
    im = im.crop((int(w * 0.22), int(h * 0.04), w, int(h * 0.82))).resize((w, h), Image.LANCZOS)
    im.filter(ImageFilter.GaussianBlur(4)).save(out, quality=90)
    return out


# ---------------------------------------------------------------- slide kinds
def build_dark_list(prs, lay, s, bg):
    sl = prs.slides.add_slide(lay)
    set_background(sl, bg)
    set_title(sl, s['title'], color=WHITE)
    blocks = [b for b in s['blocks'] if b['kind'] in ('num', 'bullet', 'p')]
    tb = new_textbox(sl, 1.4, 1.45, 7.4, 3.6)
    fill_text(tb.text_frame, blocks, 22, color=WHITE)
    return sl


def build_demo(prs, lay, s, bg):
    sl = prs.slides.add_slide(lay)
    set_background(sl, bg)
    tb = new_textbox(sl, 0.5, 2.0, 9.0, 1.6)
    tf = tb.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = s['title']
    r.font.size, r.font.bold, r.font.color.rgb = Pt(54), True, WHITE
    return sl


def build_whoami(prs, lay, s):
    sl = prs.slides.add_slide(lay)
    set_title(sl, s['title'])
    labels = [text_of(row[1]['runs']) for row in s['blocks'][0]['rows']]
    logos = [im for im in s['imgs'] if im['col'] == 0]
    for i, (im, label) in enumerate(zip(logos, labels)):
        y = TOP + 0.1 + i * 1.2
        path = ASSETS / Path(im['src']).name
        w_px, h_px = Image.open(path).size
        h = 1.0
        pic = sl.shapes.add_picture(str(path), Inches(0.8), Inches(y), height=Inches(h))
        set_alt(pic, f'{label} logo')
        tb = new_textbox(sl, 1.85, y, 3.6, h)
        tb.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        fill_text(tb.text_frame, [{'kind': 'p', 'runs': [{'t': label}]}], 20)
    head = next(im for im in s['imgs'] if im['col'] == 1)
    path = ASSETS / Path(head['src']).name
    w_px, h_px = Image.open(path).size
    h = LOGO_Y - TOP - 0.05
    pic = sl.shapes.add_picture(str(path), Inches(5.6), Inches(TOP), Inches(h * w_px / h_px), Inches(h))
    set_alt(pic, SPEAKER)
    return sl


def build_columns(prs, lay, s):
    sl = prs.slides.add_slide(lay)
    set_title(sl, s['title'])
    cols = [[b for b in s['blocks'] if b.get('col') == c] for c in (0, 1)]
    widths = (4.3, 3.75)                       # the right column stops short of the logo
    xs = (LEFT, 5.0)
    avail = BOTTOM - TOP
    # The estimate runs pessimistic in narrow columns (short bullets rarely fill
    # their last line), so allow it 5% over.
    size = next((z for z in SIZES
                 if all(text_height(c, z, w) <= avail * 1.05 for c, w in zip(cols, widths))), SIZES[-1])
    for blocks, x, w in zip(cols, xs, widths):
        tb = new_textbox(sl, x, TOP, w, avail)
        fill_text(tb.text_frame, blocks, size)
    return sl, size


def build_content(prs, lay, s):
    """Title plus a vertical flow of text groups, tables, code, and images."""
    sl = prs.slides.add_slide(lay)
    set_title(sl, s['title'])
    body = ph_by_idx(sl, 1)

    # Group consecutive text blocks; tables and code stand alone.
    groups = []
    for b in s['blocks']:
        if b['kind'] in ('table', 'code'):
            groups.append(b)
        elif groups and isinstance(groups[-1], list):
            groups[-1].append(b)
        else:
            groups.append([b])

    imgs = [im for im in s['imgs'] if not im['src'].startswith('../')]
    if imgs and not groups:
        if body is not None:
            drop(body)
        im = imgs[0]
        fit_picture(sl, ROOT / im['src'], im['alt'])
        return sl, None

    def heights(size, width):
        hs = []
        for g in groups:
            if isinstance(g, list):
                hs.append(text_height(g, size, width))
            elif g['kind'] == 'table':
                hs.append(table_height(g['rows'], table_size(size), width))
            else:
                hs.append(code_height(g['text'], width))
        return hs

    avail = BOTTOM - TOP
    chosen = None
    for size in SIZES:
        for width in (WIDTH, LOGO_X - LEFT - 0.1):
            hs = heights(size, width)
            total = sum(hs) + GAP * (len(hs) - 1)
            # full width is fine as long as nothing reaches down into the logo
            if total <= avail and (width < WIDTH or TOP + total <= LOGO_Y):
                chosen = (size, width, hs)
                break
        if chosen:
            break
    if chosen is None:
        size, width = SIZES[-1], LOGO_X - LEFT - 0.1
        chosen = (size, width, heights(size, width))
        print(f"  WARNING: '{s['title']}' may overflow at {size}pt")
    size, width, hs = chosen

    y = TOP
    used_body = False
    for g, h in zip(groups, hs):
        if isinstance(g, list):
            if not used_body and body is not None:
                tb, used_body = body, True
                tb.left, tb.top, tb.width, tb.height = Inches(LEFT), Inches(y), Inches(width), Inches(h)
            else:
                tb = new_textbox(sl, LEFT, y, width, h)
            fill_text(tb.text_frame, g, size)
        elif g['kind'] == 'table':
            add_table(sl, g['rows'], LEFT, y, width, table_size(size))
        else:
            add_code(sl, g['text'], LEFT, y, width)
        y += h + GAP
    if body is not None and not used_body:
        drop(body)
    return sl, size


# ---------------------------------------------------------------- main
prs = Presentation(str(TPL))
masters = prs.slide_masters
LAY = {l.name: l for l in masters[0].slide_layouts}
LAY_CONTENT, LAY_TITLE_ONLY, LAY_BLANK = LAY['Title and Content'], LAY['Title Only'], LAY['Blank']
TITLE_S, SURVEY_S, BLANK_S = prs.slides[0], prs.slides[1], prs.slides[2]
N_TPL = len(prs.slides)
DARK_BG = dark_background(prs)

built = []
for i, s in enumerate(SLIDES, 1):
    if i == 1:
        continue                                   # the template's own title slide
    title = s['title'] or ''
    if title == 'Agenda':
        sl, kind = build_dark_list(prs, LAY_TITLE_ONLY, s, DARK_BG), 'agenda'
    elif title == 'Demo Time':
        sl, kind = build_demo(prs, LAY_BLANK, s, DARK_BG), 'demo'
    elif any(im['src'].startswith('../WebsiteAssets') for im in s['imgs']):
        sl, kind = build_whoami(prs, LAY_TITLE_ONLY, s), 'whoami'
    elif any('col' in b for b in s['blocks']):
        sl, size = build_columns(prs, LAY_TITLE_ONLY, s)
        kind = f'columns {size}pt'
    else:
        sl, size = build_content(prs, LAY_CONTENT, s)
        kind = 'image' if size is None else f'content {size}pt'
    if s['notes']:
        sl.notes_slide.notes_text_frame.text = s['notes']
    built.append((i, title, kind, sl))

# ---------------------------------------------------------------- template slides
def set_paragraph(p, text, size=None):
    if not p.runs:
        p.add_run()
    p.runs[0].text = text
    if size:
        p.runs[0].font.size = Pt(size)
    for r in p.runs[1:]:
        r._r.getparent().remove(r._r)


def keep_paragraphs(tf, n):
    for extra in tf.paragraphs[n:]:
        extra._p.getparent().remove(extra._p)


shapes = {sh.name: sh for sh in TITLE_S.shapes}
tf = shapes['Rectangle 3'].text_frame             # session title, two lines
set_paragraph(tf.paragraphs[0], 'Microsoft Foundry', 40)
set_paragraph(tf.paragraphs[1], 'for the Skeptical Developer', 40)
keep_paragraphs(tf, 2)
tf = shapes['Rectangle 5'].text_frame             # speaker / title / organization
set_paragraph(tf.paragraphs[0], SPEAKER)
set_paragraph(tf.paragraphs[1], COMPANY)          # no job title -- not mine to invent
keep_paragraphs(tf, 2)
tf = shapes['Text Box 7'].text_frame
set_paragraph(tf.paragraphs[0], LEVEL)
keep_paragraphs(tf, 1)

# ---------------------------------------------------------------- order & prune
sldIdLst = prs.slides._sldIdLst
ids = list(sldIdLst)
gen = ids[N_TPL:]
assert len(gen) == len(built), f'{len(gen)} generated ids vs {len(built)} built'
# The survey goes just before the closing contact slide, so it is up during Q&A
# and the contact details are the last thing on screen.
keep = [ids[0]] + gen[:-1] + [ids[1], gen[-1]]
for e in ids:
    sldIdLst.remove(e)
for e in keep:
    sldIdLst.append(e)
# The blank sample slide (ids[2]) is now unreferenced; drop its part as well.
for rel in list(prs.part.rels.values()):
    if rel.reltype.endswith('/slide') and rel.target_part is BLANK_S.part:
        prs.part.drop_rel(rel.rId)

for i, title, kind, _ in built:
    print(f'{i:>2} {title[:46]:<48} {kind}')
prs.save(str(OUT))
print(f'\n{len(keep)} slides -> {OUT}')
