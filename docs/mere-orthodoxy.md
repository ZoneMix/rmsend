# Mere Orthodoxy reader adapter

Validated against the public site on 2026-09-30. No JavaScript from the site is
executed or bundled, and no text is summarized, rewritten, or invented by an LLM.

## Supported contract

Only exact `mereorthodoxy.com`/`www.mereorthodoxy.com` hostnames and the
`/the-faith-received/read/` path use this adapter. `w` is the work name; `ws` is
accepted for legacy links. Reader pagination, highlights, and fragments are
navigation state, not export selection. The entire work is exported.

The site's own [public-slug map](https://mereorthodoxy.com/assets/data/faith-received/public-slugs.json)
maps internal IDs to public names. For example, the Keach link resolves to
`eebo-51678`. This is fetched each time so the exporter does not maintain its
own book-name catalogue.

The library base is the public origin announced by
[`read.in01.js`](https://mereorthodoxy.com/assets/js/port/read.in01.js).
[`reader-core.js`](https://mereorthodoxy.com/assets/js/port/reader-core.js)
contains the site's `loadWork` and `loadEeboCanon` contracts. The adapter
implements the following data shapes:

| Reader | Data | Export behavior |
|---|---|---|
| Classic, single | `/v1/works/SLUG/meta.json` → `single` filename → `pages` | Every English page/section, in order |
| Classic, sharded | Same metadata → each `shards[].file` → `pages` | All shards, in metadata order; declared count checked |
| EEBO | `/eebo/ID.json.gz` → `meta`, recursive `toc` | Node label, content, then child divisions in order |
| EEBO modern spelling | Optional `/eebo_modern/ID.json.gz` → `m` keyed by node path | Replace only supplied divisions; keep original elsewhere |

JSON files may be gzip-compressed or already decoded by HTTP. Classic page
text is Markdown with headings, emphasis, tables, and footnotes. EEBO is HTML,
including nested lists and margin notes. Both become sanitized HTML and go
through the same PDF/EPUB renderer and device transport as other rmsend inputs.
Footnote IDs are prefixed per section to avoid collisions across a whole work.
An exact repeated opening heading is retained once. Scripts, event handlers,
iframes, dangerous URL schemes, and reader page-break controls are removed.

`--original` skips EEBO modernization entirely. Default exports may contain a
mixture of modernized and original divisions when the site has partial coverage;
the command prints the counts. A 404 for the optional modern file is the only
network failure interpreted as an absent translation. Other HTTP/JSON errors
stop the export, including missing source shards and missing images.

## Limits

TEI-only classic works, PG, PLD, and PO families are deliberately rejected.
Their source/translation alignment and page-view contracts need their own
adapters. A classic page with no English text is also rejected: it might be a
source-only work or an untranslated section. No loading-screen fallback is used.

This is an undocumented upstream data interface, not a stability promise from
Mere Orthodoxy. If it changes, the command reports an error. Ordinary essays
continue through trafilatura; member-only text is not unlocked by this adapter.

## Verify and maintain

The offline tests use short invented payloads rather than redistributed books.
They exercise the real `fetch_article` entry point at the HTTP boundary: full
work coverage, ordered shards, alias resolution, gzip, nested divisions, partial
modernization, original mode, safe markup, and failures on incomplete work.

```bash
uv run --with-requirements requirements-dev.txt python -m unittest discover -s tests
./rmsend 'https://mereorthodoxy.com/the-faith-received/read/?w=apostles-creed' --dry-run --keep ./output
./rmsend 'https://mereorthodoxy.com/the-faith-received/read/?w=keach-medium-betwixt-two-extremes' \
  --title 'A Medium Betwixt Two Extremes' --dry-run --keep ./output
```

Before adding another format, inspect the upstream loader and source schema,
add an offline completeness test at this boundary, then compare the full source
text with the exported PDF/EPUB. Check the rendering as well as extracted text.
Do not commit downloaded works, account cookies, notebook exports, or device keys.
