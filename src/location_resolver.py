import os
import json
import time
import math
import requests
from pathlib import Path
from difflib import SequenceMatcher

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_DIR              = Path(__file__).resolve().parent.parent
CACHE_FILE            = BASE_DIR / 'data' / 'location_coords.json'
NOMINATIM_URL         = 'https://nominatim.openstreetmap.org/search'
HEADERS               = {'User-Agent': 'NepalHousePricePredictor/1.0 (student project)'}
MAX_MATCH_DISTANCE_KM = 7.0
FUZZY_THRESHOLD       = 0.82   # 0.0–1.0 — how similar names must be to fuzzy-match
NEPAL_BBOX            = [26.347, 80.058, 30.447, 88.201]

# ── Common Nepal spelling aliases ─────────────────────────────────────────────
# Handles the most frequent typos/alternate spellings without needing GPS
ALIASES = {
    'bouddha':          'Budhanilkantha',
    'boudha':           'Budhanilkantha',
    'baudha':           'Budhanilkantha',
    'new baneshwor':    'Baneshwor',
    'old baneshwor':    'Baneshwor',
    'baneshwor':        'Baneshwor',
    'maharajganj':      'Maharajgunj',
    'maharajgunge':     'Maharajgunj',
    'koteshor':         'Koteshwor',
    'koteshwar':        'Koteshwor',
    'lazimpaat':        'Lazimpat',
    'budhanilkhanta':   'Budhanilkantha',
    'budanilkantha':    'Budhanilkantha',
    'bhaisipati':       'Bhaisepati',
    'bhaisipatti':      'Bhaisepati',
    'gwarko':           'Gwarko',
    'imadole':          'Imadol',
    'kapaan':           'Kapan',
    'dhapakhel':        'Dhapasi',
    'suryabinayak':     'Suryabinayak',
    'tinkune':          'Koteshwor',
    'naxal bhatbhateni':'Naxal',
    'bhatbhateni naxal':'Naxal',
    'nagarjun':         'Nagarjung',
}

# ── Haversine distance ────────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(d_lon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ── Fuzzy string similarity ───────────────────────────────────────────────────
def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

# ── Geocoder ──────────────────────────────────────────────────────────────────
def geocode_nepal(place_name):
    try:
        params = {
            'q':            f"{place_name}, Nepal",
            'format':       'json',
            'limit':        1,
            'countrycodes': 'np',
            'viewbox':      f"{NEPAL_BBOX[1]},{NEPAL_BBOX[2]},{NEPAL_BBOX[3]},{NEPAL_BBOX[0]}",
            'bounded':      1,
        }
        resp    = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=8)
        results = resp.json()
        if results:
            return float(results[0]['lat']), float(results[0]['lon'])
    except Exception as e:
        print(f"Geocoding error for '{place_name}': {e}")
    return None, None


class LocationResolver:
    def __init__(self, model_columns, supported_locations=None):
        self.known_locations = [
            col.replace('Location_', '')
            for col in model_columns
            if col.startswith('Location_')
        ]
        extra_locations = supported_locations or []
        self.supported_locations = sorted({
            loc for loc in [*self.known_locations, *extra_locations]
            if loc and loc != 'Other'
        })
        self.coords = self._load_cache()

        # FIX: only geocode locations not yet in cache, and do it lazily
       
        missing = [
            loc for loc in self.known_locations
            if loc not in self.coords and loc != 'Other'
        ]
        if missing:
            print(f"Syncing coordinates for {len(missing)} new locations...")
            self._geocode_batch(missing)

    def _load_cache(self):
        if CACHE_FILE.exists():
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        return {}

    def _save_cache(self):
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, 'w') as f:
            json.dump(self.coords, f, indent=2)

    def _geocode_batch(self, locations):
        for loc in locations:
            lat, lon = geocode_nepal(loc)
            self.coords[loc] = {'lat': lat, 'lon': lon}
            time.sleep(1.2)   # respect Nominatim rate limit
        self._save_cache()

    def resolve(self, location_input):
        if not location_input or not location_input.strip():
            return {'resolved': None, 'method': 'empty',
                    'distance_km': None, 'note': 'No location provided'}

        raw = location_input.strip()
        loc = raw.title()

        # ── Step 1: Exact match ───────────────────────────────────────────────
        if loc in self.supported_locations:
            note = None
            method = 'exact'
            if loc not in self.known_locations:
                method = 'exact_rate_only'
                note = f"Using '{loc}' local pricing profile from limited direct listings"
            return {'resolved': loc, 'method': method, 'distance_km': 0, 'note': note}

        # ── Step 2: Alias lookup (common Nepal spelling variants) ─────────────
        alias = ALIASES.get(raw.lower()) or ALIASES.get(loc.lower())
        if alias and alias in self.supported_locations:
            method = 'alias'
            note = f"Matched '{raw}' → '{alias}'"
            if alias not in self.known_locations:
                method = 'alias_rate_only'
                note = f"Matched '{raw}' → '{alias}' and used limited local pricing data"
            return {'resolved': alias, 'method': method,
                    'distance_km': 0, 'note': note}

        # ── Step 3: Fuzzy string match against known locations ────────────────
        # Catches typos like 'Budhanilkhanta' → 'Budhanilkantha' without GPS
        best_fuzzy, best_score = None, 0.0
        for known in self.supported_locations:
            score = similarity(loc, known)
            if score > best_score:
                best_score, best_fuzzy = score, known

        if best_score >= FUZZY_THRESHOLD:
            method = 'fuzzy'
            note = f"Did you mean '{best_fuzzy}'? (matched from '{raw}')"
            if best_fuzzy not in self.known_locations:
                method = 'fuzzy_rate_only'
                note = (
                    f"Matched '{raw}' to '{best_fuzzy}' and used limited local pricing data"
                )
            return {
                'resolved':    best_fuzzy,
                'method':      method,
                'distance_km': 0,
                'note':        note,
            }

        # ── Step 4: GPS geocode + nearest known location ──────────────────────
        lat, lon = geocode_nepal(loc)
        if not lat or not lon:
            # FIX: GPS failed — fall back gracefully instead of returning None
            # Try city-level geocode as last resort
            city_guess = loc.split()[0] if ' ' in loc else None
            if city_guess:
                lat, lon = geocode_nepal(city_guess)

        if not lat or not lon:
            return {'resolved': None, 'method': 'failed',
                    'distance_km': None,
                    'note': f"Could not find '{raw}' — using average pricing"}

        # Find nearest known location by GPS distance
        best_loc, best_dist = None, float('inf')
        for k_loc in self.known_locations:
            if k_loc == 'Other':
                continue
            c = self.coords.get(k_loc, {})
            if c.get('lat') and c.get('lon'):
                d = haversine(lat, lon, c['lat'], c['lon'])
                if d < best_dist:
                    best_dist, best_loc = d, k_loc

        if best_loc and best_dist <= MAX_MATCH_DISTANCE_KM:
            return {
                'resolved':    best_loc,
                'method':      'nearest_gps',
                'distance_km': round(best_dist, 2),
                'note':        (
                    f"No direct match for '{raw}' — using nearest trained area: "
                    f"{best_loc} ({round(best_dist,1)}km away)"
                )
            }

        # ── Step 5: Out of range — use None, model falls back to city rate ────
        note = (f"Nearest match ({best_loc}) is {round(best_dist,1)}km away — "
                f"using city average pricing") if best_loc else "No nearby location found"
        return {
            'resolved':    None,
            'method':      'out_of_bounds',
            'distance_km': round(best_dist, 2) if best_loc else None,
            'note':        note,
        }
