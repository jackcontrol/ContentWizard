## 🔴 Site Sentinel — 12 confirmed issue(s) · 2026-07-23 10:36 UTC

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
- **`/technical-faq`** · `anchor_target` — no element with id="mix-prep" — sitewide #mix-prep links will not jump
- **`/mixing`** · `title` — <title> missing expected text
  
  ```
  expected to contain: 'Heavy Music Mixing | Enormous Door Mixing Team' | got: 'Heavy Music Mixing for Punk, Hardcore & Metal — ENORMOUS DOOR MASTERING'
  ```
- **`/about`** · `http_status` — expected 200, got 404

Full report: `reports/latest.md`
