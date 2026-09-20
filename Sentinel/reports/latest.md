# Sentinel run — 2026-09-20 13:04 UTC

Result: **🔴 16 confirmed issue(s)** · 2 warning(s) · 2 note(s)

## Confirmed failures

- `/pricing` **forbidden_pattern** — stale/forbidden pattern present: '"price"\\s*:\\s*"?620'
  
  ```
  ed release formats.",                   "price": "620",                   "priceCurrency": "U
  ```
- `/pricing` **jsonld_type** — expected JSON-LD @type WebPage not found
  
  ```
  found: ['LocalBusiness', 'Organization', 'WebSite']
  ```
- `/pricing` **jsonld_type** — expected JSON-LD @type BreadcrumbList not found
  
  ```
  found: ['LocalBusiness', 'Organization', 'WebSite']
  ```
- `/pricing` **jsonld_type** — expected JSON-LD @type Service not found
  
  ```
  found: ['LocalBusiness', 'Organization', 'WebSite']
  ```
- `/pricing` **jsonld_type** — expected JSON-LD @type FAQPage not found
  
  ```
  found: ['LocalBusiness', 'Organization', 'WebSite']
  ```
- `/pricing` **jsonld_count** — expected 2× @type Service, found 0
- `/pricing` **jsonld_price** — price 500 missing from JSON-LD
  
  ```
  prices found: []
  ```
- `/pricing` **jsonld_price** — price 600 missing from JSON-LD
  
  ```
  prices found: []
  ```
- `/pricing` **jsonld_price** — price 850 missing from JSON-LD
  
  ```
  prices found: []
  ```
- `/launch-contact` **noindex** — page is served with a noindex directive
- `/launch-contact` **required_link** — no <a> pointing to /technical-faq#mix-prep (bare /technical-faq exists — anchor was dropped; in Squarespace, paste the full path into the URL field rather than picking the page from the dropdown)
- `/launch-contact` **required_pattern** — pattern not found: 'Band Name'
- `/launch-contact` **required_pattern** — pattern not found: 'Mixing and Mastering'
- `/technical-faq` **anchor_target** — no element with id="mix-prep" — sitewide #mix-prep links will not jump
- `/mixing` **title** — <title> missing expected text
  
  ```
  expected to contain: 'Heavy Music Mixing | Enormous Door Mixing Team' | got: 'Heavy Music Mixing for Punk, Hardcore & Metal — ENORMOUS DOOR MASTERING'
  ```
- `/about` **http_status** — expected 200, got 404

## Warnings

- `/launch-contact` **sitemap_missing** — page not listed in sitemap.xml
- `/about` **sitemap_missing** — page not listed in sitemap.xml

## Notes

- `GLOBAL` **ssl_ok** — TLS certificate valid for 59 more days
- `/gear` **content_changed** — page content changed (last change 2026-09-11 12:51 UTC -> now)
  
  ```
  --- previous
+++ current
@@ -1,4 +1,4 @@
 Analog Mastering Gear & Monitoring — ENORMOUS DOOR MASTERING 0 Skip to Content ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu PRICING BEYOND HEAVY MIXING Folder: VINYL Back VINYL MASTERING VINYL PRESSING VINYL TIMES Folder: INFO Back HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project ANALOG MASTERING GEAR & MONITORING Enormous Door Mastering uses a carefully chosen analog mastering chain, accurate monitoring, and purpose-built room design to make heavy music translate with weight, clarity, impact, and control
 The gear matters because mastering decisions need to survive real playback: vinyl, streaming, CD, cassette, clubs, cars, phones, headphones, and full-range systems
 The chain is built for heavy records that need power without losing definition
-Analog Outboard Gear By: Dangerous Music Tegeler Audio Louder Than Liftoff Etec Denmark Gainlab Audio Goly Audio Empirical Labs Black Box Analog Design A Designs Audio IGS Audio TK Audio Monitoring By:​ PSI Audio A17M PSI Sub A125-M Trinnov Audio ST2 Pro Acoustic Sciences Room Design Acoustic Sciences Room Treatment Mastering Software By: Tone Projects FabFilter Metric Halo Schwabe Digital Relab Development Newfangled Audio Weiss Digital Leapwing Audio Tokyo Dawn Labs Oeksound Pulsar Modular Kiive Audio Acustica Audio Mathew Lane Audio Sabol Hill Izotope Thimeo Audio Technology Hacienda Audio START YOUR PROJECT ENORMOUS DO
  ```

