# PowerPoint build

Regenerates `Microsoft-Foundry-for-the-Skeptical-Developer.pptx` (repo root) from
`index.html` using the Live! 360 Orlando 2026 speaker template. Run it whenever
the reveal.js deck changes. Adapted from `Pick-Your-Poison/tools/pptx-build`,
which targets the PASS Summit template.

## Requirements

- `python-pptx` and `Pillow` (a virtualenv is fine — they are not installable
  system-wide under PEP 668); `markitdown[pptx]` for checking the output
- The template. `build.py` defaults to
  `~/Downloads/L360OR26_Speaker Slide Template.pptx`; pass another path as its
  only argument.
- `../WebsiteAssets` beside this repo, for the Who Am I logos and headshot

## Steps

```bash
python extract.py          # index.html -> slides.json
python build.py            # slides.json + template -> ../../Microsoft-Foundry-for-the-Skeptical-Developer.pptx
```

`slides.json` and `dark-bg.jpg` are intermediate files and are git-ignored. The
template is small (about 460 KB, 12 layouts), so there is no layout pruning step.

## Mapping

| Reveal section | PowerPoint treatment |
|---|---|
| Title | Template title slide, filled in. Level is set to **Intermediate**. |
| Who Am I | Logos and labels on the left, headshot on the right |
| Agenda (x5) | Dark gradient, numbered list, current section in the title slide's sky blue |
| Demo Time (x4) | Dark gradient, centred 54pt |
| Twelve Requests (x2) | Screenshot, largest fit that clears the logo |
| Who Should Adopt This | Two text columns |
| Everything else | "Title and Content", with tables and the code block as native objects |
| — | Template Session Survey slide, just before the closing contact slide |

The template's blank sample slide is dropped.

## Notes

- **The logo corner.** Every content slide has the Live! 360 badge at about
  x 8.85–9.78 in, y 4.63–5.38 in on a 10 × 5.625 in slide. Anything full-width
  stops above y = 4.55 in; anything that runs lower stops short of x = 8.75 in.
  `build.py` picks the largest font size (20, 18, 16, then 14pt) and width that
  satisfy that.
- **Sizing is estimated, not measured.** Text height comes from character
  counts at 0.45 em per glyph. LibreOffice has no Calibri here and substitutes a
  wider font, so a render that fits will fit with room to spare in PowerPoint.
- **The dark slides** reuse the title slide's gradient, cropped clear of the
  event badge and brand strip baked into that image, then lightly blurred. It
  is generated from the template on each build, so a new template year picks
  up its own artwork.
- **Bullets and indents are set explicitly** on every paragraph, so text in the
  body placeholder and in added text boxes looks identical. Plain paragraphs get
  `buNone` with no hanging indent; the template's body style would otherwise
  indent them like bullets.
- **Code** is sized so its longest line fits unwrapped (14pt down to 10pt).
- Speaker notes, links, bold, italics, inline code, and image alt text carry
  across. Fragments are flattened — everything on a slide shows at once.
- The survey slide's text runs under its QR code. That is the conference's own
  template; it is left as supplied.
- **Set all four of left/top/width/height together** when moving a placeholder
  (see the Pick-Your-Poison README for why).
