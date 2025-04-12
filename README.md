# Google Scholar Citation Tracker Badge

[![Deploy to Vercel](https://github.com/dexhunter/google-scholar-badge/actions/workflows/deploy.yml/badge.svg)](https://github.com/dexhunter/google-scholar-badge/actions/workflows/deploy.yml)

Get your Google Scholar citation tracker badge!

I have developed a simple API to fetch your Google Scholar citation count and generate a badge for your profile. This badge can be easily integrated into your GitHub profile or used in various projects to showcase your citation count.

## Features

- Fetch your Google Scholar citation count
- Generate a badge with your citation count
- Easy to integrate into your GitHub profile or projects

## Usage

1. Go to [shields.io endpoint badge](https://shields.io/badges/endpoint-badge)
2. Set the endpoint to `https://google-scholar-badge.vercel.app/citations?user={user}` Replace `{user}` with your Google Scholar User ID

Can also view a playwright version [here on replit](https://replit.com/@dexhunter/google-scholar-citation-tracker)

## Example Badge

[![](https://img.shields.io/endpoint?url=https%3A%2F%2Fgoogle-scholar-badge.vercel.app%2Fcitations%3Fuser%3D8Ez_u30AAAAJ)](https://scholar.google.com/citations?user=8Ez_u30AAAAJ)

## ❗ Known Limitations

Google Scholar employs anti-bot measures that often block requests coming directly from server environments like Vercel (where this service is hosted). When a request is blocked (resulting in a `403 Forbidden` error), the service cannot retrieve the citation count and will default to displaying "0".

Attempts to mitigate this using standard browser headers have been insufficient for reliable operation. For consistent results, alternative methods like using a dedicated third-party scraping API or manual updates might be necessary.

## Work In Progress (WIP)

* deploy the service to heroku or other cloud services
* more badges (hindex, i10index, etc.)
* some tests