import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import os

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL    = "https://www.nepalhomes.com"
SEARCH_URL  = "https://www.nepalhomes.com/search"
OUTPUT_FILE = "data/scraped_raw.csv"
MAX_PAGES   = 100       # ~20 listings per page → ~2000 listings
DELAY       = 2.0       # seconds between requests (be polite)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

# ── Parsers ───────────────────────────────────────────────────────────────────
def parse_price_npr(text):
    """Convert 'Rs. 2.5 Cr' or 'Rs. 75 Lakh' → NPR integer"""
    if not text: return None
    text = text.strip().replace(',', '')
    text = re.sub(r'Rs\.?\s*', '', text, flags=re.IGNORECASE).strip()
    try:
        if re.search(r'cr', text, re.IGNORECASE):
            return float(re.sub(r'[^\d.]', '', text)) * 10_000_000
        elif re.search(r'lakh|lac|l', text, re.IGNORECASE):
            return float(re.sub(r'[^\d.]', '', text)) * 100_000
        else:
            return float(re.sub(r'[^\d.]', '', text))
    except:
        return None

def parse_area_anna(text):
    """Convert '4.2 aana' or '3 anna' → float"""
    if not text: return None
    match = re.search(r'(\d+\.?\d*)', str(text))
    return float(match.group(1)) if match else None

def parse_road_ft(text):
    """Convert '13 Feet' or '12 ft' → float"""
    if not text: return None
    match = re.search(r'(\d+\.?\d*)', str(text))
    return float(match.group(1)) if match else None

def parse_int(text):
    if not text: return None
    match = re.search(r'(\d+)', str(text))
    return int(match.group(1)) if match else None

# ── Scrape listing page ───────────────────────────────────────────────────────
def scrape_listing(url):
    """Scrape a single property detail page"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, 'html.parser')

        data = {'source_url': url}

        # ── Price ────────────────────────────────────────────────────────────
        price_el = (soup.find('span', class_=re.compile(r'price', re.I)) or
                    soup.find('div',  class_=re.compile(r'price', re.I)) or
                    soup.find('h2',   class_=re.compile(r'price', re.I)))
        data['Price_NPR'] = parse_price_npr(price_el.get_text() if price_el else None)

      
        overview = soup.find_all('div', class_=re.compile(r'overview|detail|spec|feature', re.I))

        full_text = soup.get_text(separator=' ')

        # Land area
        area_match = re.search(r'(\d+\.?\d*)\s*(aana|anna|ropani)', full_text, re.I)
        data['Area_Anna'] = float(area_match.group(1)) if area_match else None

        # Road width
        road_match = re.search(r'(\d+\.?\d*)\s*(?:feet|ft|foot)\s*road', full_text, re.I)
        if not road_match:
            road_match = re.search(r'road[^\d]*(\d+\.?\d*)\s*(?:feet|ft)', full_text, re.I)
        data['Road_Width_Ft'] = float(road_match.group(1)) if road_match else None

        # Bedrooms
        bed_match = re.search(r'(\d+)\s*(?:bed|bedroom|bhk)', full_text, re.I)
        data['BHK'] = int(bed_match.group(1)) if bed_match else None

        # Bathrooms
        bath_match = re.search(r'(\d+)\s*(?:bath|bathroom)', full_text, re.I)
        data['Bathrooms'] = int(bath_match.group(1)) if bath_match else None

        # Floors
        floor_match = re.search(r'(\d+\.?\d*)\s*(?:storey|story|storied|floor)', full_text, re.I)
        data['Floors'] = float(floor_match.group(1)) if floor_match else None

        # ── Location ─────────────────────────────────────────────────────────
        loc_el = (soup.find('span', class_=re.compile(r'location|address', re.I)) or
                  soup.find('div',  class_=re.compile(r'location|address', re.I)) or
                  soup.find('p',    class_=re.compile(r'location|address', re.I)))

        if loc_el:
            loc_text = loc_el.get_text().strip()
            # Take first part before comma
            data['Location'] = loc_text.split(',')[0].strip()
            data['District']  = loc_text.split(',')[1].strip() if ',' in loc_text else None
        else:
            # Try meta tags
            meta_loc = soup.find('meta', property='og:description')
            if meta_loc:
                content = meta_loc.get('content', '')
                loc_match = re.search(r'at\s+([^,\.]+)', content, re.I)
                data['Location'] = loc_match.group(1).strip() if loc_match else None
            data['District'] = None

        return data

    except Exception as e:
        print(f"  Error scraping {url}: {e}")
        return None


# ── Collect listing URLs from search pages ────────────────────────────────────
def get_listing_urls(page):
    """Get all property detail URLs from a search results page"""
    params = {
        'find_property_category': '5d660cb27682d03f547a6c4a',  # House category
        'find_listing_type':      'sale',
        'page':                   page,
    }
    try:
        resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, 'html.parser')

        urls = []
        # Find all property card links
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/detail/' in href or '/property/' in href:
                full_url = href if href.startswith('http') else BASE_URL + href
                if full_url not in urls:
                    urls.append(full_url)
        return urls

    except Exception as e:
        print(f"  Error fetching page {page}: {e}")
        return []


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    os.makedirs('data', exist_ok=True)

    all_records = []
    seen_urls   = set()

    # Load existing data if resuming
    if os.path.exists(OUTPUT_FILE):
        existing = pd.read_csv(OUTPUT_FILE)
        all_records = existing.to_dict('records')
        seen_urls   = set(existing.get('source_url', []))
        print(f"Resuming — {len(all_records)} records already scraped")

    print(f"Starting scrape of nepalhomes.com (up to {MAX_PAGES} pages)...\n")

    for page in range(1, MAX_PAGES + 1):
        print(f"Page {page}/{MAX_PAGES} — collecting listing URLs...")
        urls = get_listing_urls(page)

        if not urls:
            print(f"No listings found on page {page} — stopping.")
            break

        new_urls = [u for u in urls if u not in seen_urls]
        print(f"  Found {len(urls)} listings, {len(new_urls)} new")

        for i, url in enumerate(new_urls):
            record = scrape_listing(url)
            if record and record.get('Price_NPR') and record.get('Area_Anna'):
                all_records.append(record)
                seen_urls.add(url)
                print(f"  [{len(all_records)}] {record.get('Location','?'):20} "
                      f"| {record.get('Area_Anna','?')} Anna "
                      f"| {record.get('BHK','?')} BHK "
                      f"| NPR {record.get('Price_NPR',0):,.0f}")
            time.sleep(DELAY)

        # Save after every page
        pd.DataFrame(all_records).to_csv(OUTPUT_FILE, index=False)
        print(f"  Saved {len(all_records)} total records to {OUTPUT_FILE}")
        time.sleep(DELAY)

    print(f"\nDone! Total records scraped: {len(all_records)}")
    print(f"Saved to: {OUTPUT_FILE}")

    # Quick stats
    df = pd.DataFrame(all_records)
    print(f"\nStats:")
    print(f"  Rows with price    : {df['Price_NPR'].notna().sum()}")
    print(f"  Rows with area     : {df['Area_Anna'].notna().sum()}")
    print(f"  Rows with BHK      : {df['BHK'].notna().sum()}")
    print(f"  Unique locations   : {df['Location'].nunique()}")


if __name__ == '__main__':
    main()