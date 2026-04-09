import pandas as pd
import numpy as np
import re

df = pd.read_csv('data/kaggle_nepal.csv')
print(f"Raw rows loaded: {len(df)}")

# ── Parsers ───────────────────────────────────────────────────────────────────
def parse_price(s):
    if pd.isna(s): return np.nan
    s = str(s).strip().replace(',', '')
    # FIX: skip rental prices like "Rs. 2.5 Lac/m" — /m means per month
    if re.search(r'/m|per.?month', s, re.IGNORECASE): return np.nan
    s = re.sub(r'Rs\.?\s*', '', s, flags=re.IGNORECASE).strip()
    try:
        if re.search(r'cr', s, re.IGNORECASE):
            return float(re.sub(r'[^\d.]', '', s)) * 10_000_000
        elif re.search(r'lakh|lac', s, re.IGNORECASE):
            return float(re.sub(r'[^\d.]', '', s)) * 100_000
        else:
            return float(re.sub(r'[^\d.]', '', s))
    except:
        return np.nan

def parse_area(s):
    if pd.isna(s): return np.nan
    match = re.search(r'(\d+\.?\d*)', str(s))
    return float(match.group(1)) if match else np.nan

def parse_road(s):
    # FIX: handle ranges like "10-15 Feet", "14/26 Feet" → take average
    if pd.isna(s): return np.nan
    s = str(s)
    nums = re.findall(r'(\d+\.?\d*)', s)
    if not nums: return np.nan
    vals = [float(n) for n in nums]
    return sum(vals) / len(vals)   # average of range, or single value

def parse_location(s):
    if pd.isna(s): return np.nan
    return str(s).split(',')[0].strip().title()

def parse_city(s):
    if pd.isna(s): return np.nan
    parts = str(s).split(',')
    return parts[-1].strip().title() if len(parts) > 1 else np.nan

# ── City normalisation ────────────────────────────────────────────────────────
CITY_MAP = {
    'kathmandu':   'Kathmandu',
    'kathmandhu':  'Kathmandu',
    'karhmandu':   'Kathmandu',
    'lalitpur':    'Lalitpur',
    'bhaktapur':   'Bhaktapur',
    'sitapaila':   'Kathmandu',
    'narayanthan': 'Kathmandu',
    'rumba chowk': 'Kathmandu',
    'imadol':      'Lalitpur',
}

def normalise_city(s):
    if pd.isna(s): return 'Other'
    return CITY_MAP.get(str(s).strip().lower(), str(s).strip().title())

# ── Transform ─────────────────────────────────────────────────────────────────
df['Price_NPR']     = df['PRICE'].apply(parse_price)
df['Area_Anna']     = df['LAND AREA'].apply(parse_area)
df['Road_Width_Ft'] = df['ROAD ACCESS'].apply(parse_road)
df['Location']      = df['LOCATION'].apply(parse_location)
df['City']          = df['LOCATION'].apply(parse_city).apply(normalise_city)
df['District']      = df['City']
df['BHK']           = pd.to_numeric(df['BEDROOM'],  errors='coerce')
df['Bathrooms']     = pd.to_numeric(df['BATHROOM'], errors='coerce')
df['Floors']        = pd.to_numeric(df['FLOOR'],    errors='coerce')

# ── Sale listings only ────────────────────────────────────────────────────────
df = df[df['TITLE'].str.contains('sale', case=False, na=False)]
print(f"After sale filter: {len(df)} rows")

# ── Select columns ────────────────────────────────────────────────────────────
clean = df[['City','District','Location','BHK','Bathrooms',
            'Floors','Area_Anna','Road_Width_Ft','Price_NPR']].copy()

# ── FIX: Impute missing BHK/Bathrooms/Floors instead of dropping them ─────────
# A Naxal listing with known price+area but missing BHK is still valuable
# Use median per location, fall back to global median
for col in ['BHK', 'Bathrooms', 'Floors']:
    loc_median = clean.groupby('Location')[col].transform('median')
    global_median = clean[col].median()
    clean[col] = clean[col].fillna(loc_median).fillna(global_median)

# Road width: fill missing with location median, then global
loc_road = clean.groupby('Location')['Road_Width_Ft'].transform('median')
clean['Road_Width_Ft'] = clean['Road_Width_Ft'].fillna(loc_road).fillna(12.0)

# ── Drop rows still missing critical fields after imputation ──────────────────
before = len(clean)
clean.dropna(subset=['Price_NPR', 'Area_Anna'], inplace=True)

# ── Remove impossible values ──────────────────────────────────────────────────
clean = clean[clean['Bathrooms'] <= clean['BHK'] + 3]

# ── Remove outliers ───────────────────────────────────────────────────────────
clean = clean[(clean['Price_NPR']     >= 1_000_000) & (clean['Price_NPR']     <= 500_000_000)]
clean = clean[(clean['Area_Anna']     >= 0.5)       & (clean['Area_Anna']     <= 50)]
clean = clean[(clean['BHK']           >= 1)         & (clean['BHK']           <= 15)]
clean = clean[(clean['Road_Width_Ft'] >= 4)         & (clean['Road_Width_Ft'] <= 100)]

clean = clean.reset_index(drop=True)
after = len(clean)

print(f"Clean rows : {after}  (removed {before - after} rows)")
print(f"Price range: NPR {clean['Price_NPR'].min():,.0f} — {clean['Price_NPR'].max():,.0f}")
print(f"Cities     : {sorted(clean['City'].unique())}")
print(f"Locations  : {clean['Location'].nunique()} unique")

# ── Show recovered premium locations ─────────────────────────────────────────
print(f"\nPremium location row counts:")
for loc in ['Naxal','Thamel','Maharajgunj','Baluwatar','Lazimpat','Sanepa','Baneshwor']:
    rows = clean[clean['Location'] == loc]
    if len(rows):
        ppa = (rows['Price_NPR'] / rows['Area_Anna']).median()
        print(f"  {loc:20s}: {len(rows):3d} rows | NPR {ppa/1e5:.1f}L/anna")
    else:
        print(f"  {loc:20s}:   0 rows")

clean.to_csv('data/nepal_house_data.csv', index=False)
print("\nSaved to data/nepal_house_data.csv")

