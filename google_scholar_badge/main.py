from fastapi import FastAPI
import httpx
from bs4 import BeautifulSoup
import uvicorn  # For running the server

app = FastAPI()


async def get_citation_number(url: str):
    async with httpx.AsyncClient() as client:
        # Add headers to mimic a browser request, which can sometimes help
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = await client.get(url, headers=headers, follow_redirects=True)
        # Handle potential errors during the request
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the stats table by its ID
        stats_table = soup.find('table', {'id': 'gsc_rsb_st'})
        if stats_table:
            # Find the 'Citations' label within the table
            # Using a lambda to be more flexible in finding the link text
            citations_label = stats_table.find(lambda tag: tag.name == 'a' and 'citations' in tag.get('href', '').lower())
            if citations_label:
                # Navigate up to the parent row (tr)
                row = citations_label.find_parent('tr')
                if row:
                    # Find the sibling td element containing the count
                    citation_element = row.find('td', {'class': 'gsc_rsb_std'})
                    if citation_element:
                        return citation_element.text.strip() # Strip any extra whitespace
        # Fallback or if the structure is completely different
        return None


@app.get("/citations")
async def get_citations(user: str):
    url = f"https://scholar.google.com/citations?user={user}"
    citation_count = await get_citation_number(url)

    if citation_count:
        return {
            "schemaVersion": 1,
            "label": "Citations",
            "message": citation_count,
            "style": "social",
            "namedLogo": "Google Scholar"
        }
    else:
        return {
            "schemaVersion": 1,
            "label": "Citations",
            "message": 0,
            "style": "social",
            "namedLogo": "Google Scholar"
        }


# Ensure this block works properly
if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
