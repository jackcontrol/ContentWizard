## 🔴 Site Sentinel — 16 confirmed issue(s) · 2026-07-19 10:02 UTC

Each issue below failed an initial check **and** a fresh cache-busted re-fetch, so these are not cache ghosts.

- **`/pricing`** · `forbidden_pattern` — stale/forbidden pattern present: '"price"\\s*:\\s*"?620'
  
  ```
  ed release formats.",                   "price": "620",                   "priceCurrency": "U
  ```
- **`/pricing`** · `jsonld_type` — expected JSON-LD @type WebPage not found
  
  ```
  found: ['LocalBusiness', 'Organization', 'WebSite']
  ```
- **`/pricing`** · `jsonld_type` — expected JSON-LD @type BreadcrumbList not found
  
  ```
  found: ['LocalBusiness', 'Organization', 'WebSite']
  ```
- **`/pricing`** · `jsonld_type` — expected JSON-LD @type Service not found
  
  ```
  found: ['LocalBusiness', 'Organization', 'WebSite']
  ```
- **`/pricing`** · `jsonld_type` — expected JSON-LD @type FAQPage not found
  
  ```
  found: ['LocalBusiness', 'Organization', 'WebSite']
  ```
- **`/pricing`** · `jsonld_count` — expected 2× @type Service, found 0
- **`/pricing`** · `jsonld_price` — price 500 missing from JSON-LD
  
  ```
  prices found: []
  ```
- **`/pricing`** · `jsonld_price` — price 600 missing from JSON-LD
  
  ```
  prices found: []
  ```
- **`/pricing`** · `jsonld_price` — price 850 missing from JSON-LD
  
  ```
  prices found: []
  ```
- **`/launch-contact`** · `noindex` — page is served with a noindex directive
- **`/launch-contact`** · `required_link` — no <a> pointing to /technical-faq#mix-prep (bare /technical-faq exists — anchor was dropped; in Squarespace, paste the full path into the URL field rather than picking the page from the dropdown)
- **`/launch-contact`** · `required_pattern` — pattern not found: 'Band Name'
- **`/launch-contact`** · `required_pattern` — pattern not found: 'Mixing and Mastering'
- **`/technical-faq`** · `anchor_target` — no element with id="mix-prep" — sitewide #mix-prep links will not jump
- **`/mixing`** · `title` — <title> missing expected text
  
  ```
  expected to contain: 'Heavy Music Mixing | Enormous Door Mixing Team' | got: 'Heavy Music Mixing for Punk, Hardcore & Metal — ENORMOUS DOOR MASTERING'
  ```
- **`/about`** · `http_status` — expected 200, got 404

Full report: `reports/latest.md`
