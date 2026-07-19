# Sentinel run — 2026-07-19 10:02 UTC

Result: **🔴 16 confirmed issue(s)** · 2 warning(s) · 5 note(s)

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

- `GLOBAL` **ssl_ok** — TLS certificate valid for 67 more days
- `/pricing` **content_changed** — page content changed (last change 2026-07-10 16:37 UTC -> now)
  
  ```
  --- previous
+++ current
@@ -1,13 +1,14 @@
-Heavy Music Mastering Pricing | Enormous Door Mastering — ENORMOUS DOOR MASTERING 0 Skip to Content ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu PRICING BEYOND HEAVY MIXING Folder: VINYL Back VINYL MASTERING VINYL PRESSING VINYL TIMES Folder: INFO Back HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Mastering Pricing Heavy Music Mastering PRICING Clear mastering prices for single-format masters, full release packages, and Beyond Heavy collaborative mastering
+Heavy Music Mastering Pricing | Enormous Door Mastering — ENORMOUS DOOR MASTERING 0 Skip to Content ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu PRICING BEYOND HEAVY MIXING Folder: VINYL Back VINYL MASTERING VINYL PRESSING VINYL TIMES Folder: INFO Back HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Mastering Pricing Heavy Music Mastering PRICING
  ```
- `/mixing` **content_changed** — page content changed (last change 2026-07-10 16:37 UTC -> now)
  
  ```
  --- previous
+++ current
@@ -1,4 +1,4 @@
-Heavy Music Mixing | Enormous Door Mixing Team — ENORMOUS DOOR MASTERING 0 Skip to Content ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu PRICING BEYOND HEAVY MIXING Folder: VINYL Back VINYL MASTERING VINYL PRESSING VINYL TIMES Folder: INFO Back HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project HEAVY MUSIC MIXING A curated mixing network for punk, hardcore, metal, doom, death metal, black metal, grind, noise, industrial, ambient, and extreme releases
+Heavy Music Mixing for Punk, Hardcore & Metal — ENORMOUS DOOR MASTERING 0 Skip to Content ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu PRICING BEYOND HEAVY MIXING Folder: VINYL Back VINYL MASTERING VINYL PRESSING VINYL TIMES Folder: INFO Back HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project HEAVY MUSIC MIXING A curated mixing network for punk, hardcore, metal, 
  ```
- `/clients` **content_changed** — page content changed (last change 2026-07-10 16:37 UTC -> now)
  
  ```
  --- previous
+++ current
@@ -1,4 +1,4 @@
-Heavy Music Mastering Clients | Enormous Door Mastering — ENORMOUS DOOR MASTERING 0 Skip to Content ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu PRICING BEYOND HEAVY MIXING Folder: VINYL Back VINYL MASTERING VINYL PRESSING VINYL TIMES Folder: INFO Back HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project HEAVY MUSIC MASTERING CLIENTS Selected Enormous Door Mastering clients, credits, label projects, and press-recognized releases across metal, punk, hardcore, doom, death metal, black metal, grind, heavy rock, vinyl, streaming, CD, cassette, and digital formats
+Heavy Music Mastering Clients — ENORMOUS DOOR MASTERING 0 Skip to Content ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu PRICING BEYOND HEAVY MIXING Folder: VINYL Back VINYL MASTERING VINYL PRESSING VINYL TIMES Folder: INFO Back HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS G
  ```
- `/gear` **content_changed** — page content changed (last change 2026-07-10 16:37 UTC -> now)
  
  ```
  --- previous
+++ current
@@ -1,4 +1,4 @@
-Analog Mastering Gear & Monitoring | Enormous Door Mastering — ENORMOUS DOOR MASTERING 0 Skip to Content ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu PRICING BEYOND HEAVY MIXING Folder: VINYL Back VINYL MASTERING VINYL PRESSING VINYL TIMES Folder: INFO Back HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project ANALOG MASTERING GEAR & MONITORING Enormous Door Mastering uses a carefully chosen analog mastering chain, accurate monitoring, and purpose-built room design to make heavy music translate with weight, clarity, impact, and control
+Analog Mastering Gear & Monitoring — ENORMOUS DOOR MASTERING 0 Skip to Content ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu ENORMOUS DOOR MASTERING PRICING BEYOND HEAVY MIXING VINYL VINYL MASTERING VINYL PRESSING VINYL TIMES INFO HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Project Open Menu Close Menu PRICING BEYOND HEAVY MIXING Folder: VINYL Back VINYL MASTERING VINYL PRESSING VINYL TIMES Folder: INFO Back HOW TO PROCEED TECHNICAL FAQ TERMS AND CONDITIONS PRIVACY POLICY UPLOAD FILES RECORDING ROADMAP GRAPHICS CLIENTS GEAR Start Your Proje
  ```

