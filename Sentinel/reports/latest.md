# Sentinel run — 2026-09-09 12:59 UTC

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

- `GLOBAL` **ssl_ok** — TLS certificate valid for 70 more days
- `/` **content_changed** — page content changed (last change 2026-07-10 16:37 UTC -> now)
  
  ```
  --- previous
+++ current
@@ -13,6 +13,8 @@
 Your mix is balanced, ready for a high-level release You want punch, clarity, and defined emotion (not just loud) You're open to making mix adjustments if asked AWARD-WINNING HEAVY MASTERING RUÏM wins the Norwegian Spellemann award for "Best Metal Album 2023" RUÏM Black Royal Spiritism..
 LP (Peaceville Records) Mastered by Jack Control VOIVOD wins the Canadian Juno award for "Best Metal Album 2023" VOIVOD Synchro Anarchy LP (Century Media Records) Mastered by Maor Appelbaum HEAR THE MASTERING DIFFERENCE Play the before/after videos to hear how mastering can add impact, clarity, weight, and translation without losing the character of the mix
 Real feedback from heavy bands mastered by Enormous Door, including black metal, doom, hardcore, punk, death metal, and extreme releases
+Newsletter Block This newsletter signup form needs a storage option
+Edit the block and enter a storage location via the Storage tab
 NOT QUITE READY? Get the Mix-Prep PDF, or review the full Mix Prep & Delivery Specs before sending final files
 Email Address Get The PDF We respect your privacy
 We aren’t going to spam you
  ```

