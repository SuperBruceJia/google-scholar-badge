# Google Scholar Citation Tracker Badge

[![Deploy](https://github.com/dexhunter/google-scholar-badge/actions/workflows/deploy.yml/badge.svg)](https://github.com/dexhunter/google-scholar-badge/actions/workflows/deploy.yml)

Display your live Google Scholar citation count anywhere you can use a Shields badge.

---

## Usage

1. Find your Google Scholar author ID (the `user=XXXX` part of the profile URL).  
2. Go to *Shields Endpoint Badge* and set the endpoint to:  
   `https://google-scholar-badge.vercel.app/citations?user=YOUR_ID`  
3. Add the generated markdown anywhere you like.

### Copy-paste badge snippet

`[![](https://img.shields.io/endpoint?url=https%3A%2F%2Fgoogle-scholar-badge.vercel.app%2Fcitations%3Fuser%3DYOUR_ID)](https://scholar.google.com/citations?user=YOUR_ID)`

Replace **YOUR_ID** with your own author ID.

---

## Example

[![](https://img.shields.io/endpoint?url=https%3A%2F%2Fgoogle-scholar-badge.vercel.app%2Fcitations%3Fuser%3D8Ez_u30AAAAJ)](https://scholar.google.com/citations?user=8Ez_u30AAAAJ)

---

## ⚠️ Limitations

* **SerpApi rate limits:** the free tier allows 100 requests / month. When exhausted, the badge shows “Rate limit” for about 10 minutes.
* **Redis optional:** without it every badge request hits SerpApi (slower and uses more credits).

---

## Roadmap (🛠 WIP)

* Badges for *h-index*, *i10-index*, yearly citations  
* Docker image & one-command deployment  
* Integration tests
