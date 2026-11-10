# AI Reference Retriever — Production Processor (Midterm, Oct-20 milestone)

Standalone Python panel matching your ASCII mockup. Photoshop-live via drag-in + JSX.

## Run
```
cd ai-reference-retriever
pip install -r requirements.txt
python app.py         # GUI
```

## What maps to your timeline
- **Oct 13**: panel GUI ✓, LOC live ✓, prompt inputs w/ constraints ✓,
  Search button ✓, metadata + thumbnails inline (no browser) ✓
- Click any thumbnail to enlarge it (full image + full attribution, approve/save
  from the popup). Cards whose preview won't download are removed, not left blank.
- **Oct 20**: NGA / Europeana connected (with honest fallbacks — see below) ✓,
  validation icons ✓ Fits / △ Post-brief / ✕ Mismatch / ? Unknown ✓,
  Approve / To-Review moodboard ✓, Save session + Export PDF / PSD+JSX ✓
  (type a brief by hand - e.g. "1890s bar in Ireland" - then click Search)

## Source honesty (risky parts you flagged)
- **OpenVerse**: back as PD-only (`license=pdm,cc0`, commercial-safe) with
  keyword-must-match on title/creator/tags. No artwork dates exist there, so its
  hits stay `?` (verify date at source) — dateless, never dateless-and-random.
- **LOC**: live keyless `fo=json` ✓ (needs browser User-Agent; retries on 403/rate-limit)
- **NGA**: real local search — `python nga_build.py` (once) downloads the Gallery's
  CC0 open-data dump (146k objects, 64k open-access images) into `data/nga.sqlite`;
  queries run full-text with brief year-overlap and IIIF images. No keyless NGA
  search API exists, so the data lives on your disk instead.
- **Picryl**: removed — no public API exists (repo 404, old API host dead, site 403s bots).
- **Europeana**: live Search API, open-license images only — add a free key in
  `.europeana_key` (or `set EUROPEANA_API_KEY=...`; see API-KEYS.txt).
- **Met**: live keyless Collection API (v1.1 search + object records), native
  dateBegin/dateEnd filtering; image URLs served for public-domain works only,
  so every Met hit is dated, hi-res, and openly reusable.
- **Commons**: live keyless MediaWiki API (site relevance order, bitmap files).
  Artwork dates come from the file's date field/filename/categories — never the
  upload timestamp; unattributable-date files stay `?` with artist + license shown.
- **Cleveland**: live keyless Open Access API (64k CC0 records), native
  created_after/created_before facet; web-size previews, print-size drag-ins
  (50MB+ .tif masters never fetched).
- **AIC**: live keyless REST API (50k+ PD/CC0 works), same-field date_start range
  facet (API takes one query clause per GET, so PD is enforced client-side);
  IIIF 400px previews, 1686px drag-ins.
- **SMK**: live keyless API; only records with `public_domain: true` and a
  CC Public Domain Mark/CC0 rights URL are returned; production date + SMK
  IIIF 843px previews / 1600px drag-ins.
- **Rijksmuseum**: live keyless Linked Art search + resolver; only image
  DigitalObjects carrying the museum's "Public Domain" statement (or CC0/PDM
  URL) are kept. The object-level CC0 metadata license is not treated as an
  image licence. Native `creationDate` wildcard (`189?`) + IIIF tiers.
- **Mia**: live keyless search API; only `rights_type: Public Domain` +  
  `Rights_Image_Display: Full` + valid image + dated records are returned;  
  Mia CDN 400px previews / full public-domain drag-ins.
- **InternetArchive**: live keyless advanced search; only items whose  
  `licenseurl` explicitly contains "publicdomain" are returned; archive image  
  service preview used for grid and drag-in.
- **Wellcome**: live keyless catalogue API (historical photos/drawings), production
  dates + per-record IIIF + license; only public-domain-marked records kept
  (mixed-rights catalogue), dated hits ranked first.
- **Harvard**: live keyed API (~250k records, strong for 19th-c. photos/prints),
  keyword search + native yearmade range facet; add a free key in `.harvard_key`
  (or `set HARVARD_API_KEY=...`; see API-KEYS.txt); do-not-display records
  skipped, IIIF 400px previews + full-res drag-ins.
- Every card shows its error state; failures degrade to `? Unknown`, never a fake ✓.

## Photoshop handoff
- `↓drag` saves full JPG to `board/` — drag straight into Photoshop.
- `Export Board (PSD+JSX)` writes `board/board.psd` (flattened contact sheet),
  `board/load_in_photoshop.jsx` (File > Scripts > Browse in Photoshop),
  `board/attribution.txt` (credits for time period / location / artist).
- `Export Board (PDF)` writes a contact sheet with source + date + validation + attribution.

## Validation rule (hand-checkable, no key)
Date parsed from metadata → compared to brief range (`1920s`=1920-29, `1890s`, `1750-1780`,
`Colonial`=1607-83). Within range = ✓, ≤12y outside = △, >35y off or excluded-term hit = ✕ (hidden from
the grid — the header shows how many were suppressed), no date / fetch fail = ?.
Topicality is enforced too: a record showing none of your prompt words (or
close synonyms like bust→portrait, saloon→bar) in its title/artist/medium is
hidden as off-topic — a bare place word doesn't count unless place is the whole
prompt. Exclusions are plural-aware ("women" catches "woman"/"ladies").
Two extra guards: book/text formats (covers, title pages) are hidden unless your
brief mentions books/covers; and under a pre-1935 brief, dateless photo-like hits
are pixel-checked as previews arrive — full-color ones are hidden as likely modern
(B&W and sepia pass; paintings are exempt; dated items are judged by date).
Search terms are keywords from your Title + Location (stopwords, dates, and
placeholder locations like "Anywhere" removed, max 4). Each source leads with
your keywords plus the period facet — i.e. what its own site shows with the
date filter ticked — in native relevance order; shortened/synonym fallbacks
fire only on empty hits and are labeled (`via variant ...`) in the attribution.
Style/mood words stay out of the query, and each source shortens further on
empty hits.

## Inside Photoshop (one tool, one folder)
The Photoshop side is the UXP panel in `uxp-plugin\`. It is the default
front-end and it drives the tool that lives in this folder - the panel itself
owns no path.

    uxp-plugin\              the panel (Photoshop > Plugins > Production Processor > Retriever)
    retriever_config.json    this folder's contract: which script launches the tool, where the board is
    install_uxp_no_admin.ps1 one installer for everything, no admin rights
    photoshop\*.jsx          legacy fallbacks (File > Scripts > ...) - they read the same pointer
    cep\                     legacy fallback panel (Window > Extensions > Retriever) - same pointer

How the panel finds this folder (first hit wins):
 1. the folder you picked in the panel (Choose Retriever Folder)
 2. the shared pointer ~\production_processor_dir.txt
 3. the known locations under your home folder
    (e.g. Downloads\ai-reference-retriever-extracted\ai-reference-retriever)

The panel then reads retriever_config.json from that folder and starts the
tool with this folder's own start_hidden.vbs (or run.bat), and opens this
folder's board\ for drag-in. It also keeps ~\production_processor_dir.txt up
to date, so the legacy JSX scripts and the CEP panel always point at the same
place.

Install (no admin, current user only):

    powershell -ExecutionPolicy Bypass -File install_uxp_no_admin.ps1

Restart Photoshop, then Plugins > Production Processor > Retriever.
The first Open Retriever click shows a UXP consent prompt - choose Allow.
