# Reading design

`assets/print.css` is the default PDF stylesheet. It was designed and used on a
reMarkable 2: 1404 × 1872 pixels at 226 DPI, approximately 157.8 × 210.4 mm.
Chrome prints at that physical page size, with no browser header or footer.

The body is 10.5 pt with 1.6 line height. Charter is preferred for its sturdy
serifs; Georgia is the fallback. Fonts are supplied by your operating system,
not distributed here. Linux may use its generic serif unless you install a
suitable, properly licensed font. That changes line wrapping, not the page box.

Margins are 16 mm top, 22 mm right, 18 mm bottom, and 14 mm left. The wider right
edge leaves room for handwriting. Text is black on white; quotations use a 2 pt
black rule. Images are grayscale with a modest contrast boost. Section headings
stay with the following content where the browser can fit them together.

The article extractor retains emphasis, links, figures, captions, and notes.
The Faith Received adapter keeps structural headings, lists, italics, and source
margin notes. Source notes appear smaller and indented alongside their paragraph.
Historical folio markers are removed so they do not split prose artificially.
Long books paginate naturally; source folios do not equal exported PDF pages.

`assets/epub.css` carries structure rather than fixed typography: the reMarkable
EPUB reader controls the font, size, spacing, margins, and justification.

## Customize without changing the project

Copy both stylesheets into a directory you control, then set `RMSEND_ASSETS`:

```bash
mkdir -p ~/.config/rmsend/styles
cp assets/print.css assets/epub.css ~/.config/rmsend/styles/
RMSEND_ASSETS=~/.config/rmsend/styles rmsend 'https://example.org/an-article'
```

For another tablet, change `@page size` and its margins in your copy of
`print.css`. The default was not measured on Paper Pro or Paper Pro Move.
Try `--dry-run --keep ./output` and inspect the result before sending it.

Local HTML deliberately brings its own stylesheet. Use the included
`examples/sample.html` as a starting point and link your chosen CSS. Do not
expect `RMSEND_ASSETS` to override a stylesheet that your HTML embeds itself.

To reproduce the README preview with Poppler installed:

```bash
./rmsend examples/sample.html --dry-run --keep ./output
pdftoppm -scale-to 1200 -png -singlefile 'output/A Little Room to Read.pdf' docs/images/sample
```

PDF metadata contains timestamps. Browser and font versions also affect layout,
so deterministic extraction does not imply identical PDF bytes across computers.
