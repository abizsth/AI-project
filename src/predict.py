import sys
import pandas as pd
import numpy as np
import pickle
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BUNDLE_PATH = BASE_DIR / 'model_bundle.pkl'

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.location_resolver import LocationResolver

# ── Load model ────────────────────────────────────────────────────────────────
try:
    if BUNDLE_PATH.exists():
        with open(BUNDLE_PATH, 'rb') as f:
            bundle = pickle.load(f)
        model = bundle['model']
        model_columns = bundle['model_columns']
        meta = bundle.get('meta', {})
    else:
        with open(BASE_DIR / 'house_model.pkl', 'rb') as f:
            model = pickle.load(f)
        with open(BASE_DIR / 'model_columns.pkl', 'rb') as f:
            model_columns = pickle.load(f)
        with open(BASE_DIR / 'model_meta.pkl', 'rb') as f:
            meta = pickle.load(f)
except FileNotFoundError:
    print("Error: Missing model files. Run train.py first!")
    exit()

log_transformed = meta.get('log_transformed', False)
rate_maps       = meta.get('rate_maps', {})
loc_rate        = rate_maps.get('loc_rate',    {})
city_rate       = rate_maps.get('city_rate',   {})
global_rate     = rate_maps.get('global_rate', 8_000_000)
resolver_locations = meta.get('resolver_locations', [])

resolver = LocationResolver(model_columns, supported_locations=resolver_locations)

CITY_MAP = {
    'kathmandu':   'Kathmandu',
    'kathmandhu':  'Kathmandu',
    'karhmandu':   'Kathmandu',
    'lalitpur':    'Lalitpur',
    'bhaktapur':   'Bhaktapur',
}

def normalize_city(city_input):
    return CITY_MAP.get(city_input.strip().lower(), city_input.strip().title())

def get_land_rates(resolved_location, city_input):
    city_norm = normalize_city(city_input)
    land_rate = (loc_rate.get(resolved_location)
                 or city_rate.get(city_norm)
                 or global_rate)
    c_rate    = city_rate.get(city_norm, global_rate)
    return float(land_rate), float(c_rate)

def ask_float(prompt, min_val=0.1, max_val=9999):
    while True:
        try:
            val = float(input(prompt))
            if val < min_val or val > max_val:
                print(f"  Please enter a value between {min_val} and {max_val}")
                continue
            return val
        except ValueError:
            print("  Please enter a valid number")

def ask_int(prompt, min_val=1, max_val=99):
    while True:
        try:
            val = int(input(prompt))
            if val < min_val or val > max_val:
                print(f"  Please enter a value between {min_val} and {max_val}")
                continue
            return val
        except ValueError:
            print("  Please enter a whole number")

def fmt(val):
    if val >= 10_000_000:
        return f"{val / 10_000_000:.2f} Crore"
    if val >= 100_000:
        return f"{val / 100_000:.2f} Lakh"
    return f"NPR {val:,.0f}"

def build_input(area, bhk, bath, floors, road, resolved, city_input):
    input_df = pd.DataFrame(0, index=[0], columns=model_columns)
    input_df['Area_Anna']     = area
    input_df['BHK']           = bhk
    input_df['Bathrooms']     = bath
    input_df['Floors']        = floors
    input_df['Road_Width_Ft'] = road
    input_df['BHK_per_Anna']  = bhk  / area if area > 0 else 0
    input_df['Bath_per_BHK']  = bath / bhk if bhk > 0 else 0
    input_df['Area_x_Floors'] = area * floors
    input_df['Road_x_Area']   = road * area

    land_rate, c_rate = get_land_rates(resolved or '', city_input)
    if 'loc_land_rate'  in input_df.columns: input_df['loc_land_rate']  = land_rate
    if 'city_land_rate' in input_df.columns: input_df['city_land_rate'] = c_rate

    city_col = 'City_' + normalize_city(city_input)
    if city_col in input_df.columns:
        input_df[city_col] = 1
    elif 'City_Other' in input_df.columns:
        input_df['City_Other'] = 1

    if resolved:
        col = 'Location_' + resolved
        if col in input_df.columns:
            input_df[col] = 1

    return input_df

# ── Main ──────────────────────────────────────────────────────────────────────
print("\n--- NEPAL HOUSE PRICE PREDICTOR ---\n")

loc_input  = input("Location: ").strip()
city_input = input("City: ").strip()
area       = ask_float("Area in Anna: ", 0.1, 50)
bhk        = ask_int(  "Bedrooms / BHK: ", 1, 15)
bath       = ask_int(  "Bathrooms: ", 1, 20)
floors     = ask_float("Total Floors: ", 0.5, 10)
road       = ask_float("Road Width in ft: ", 4, 100)

result   = resolver.resolve(loc_input)
resolved = result.get('resolved')
note     = result.get('note', '')

if note:
    print(f"\n  {note}")

input_df   = build_input(area, bhk, bath, floors, road, resolved, city_input)
raw        = model.predict(input_df)[0]
prediction = float(np.exp(raw)) if log_transformed else float(raw)
low        = prediction * 0.88
high       = prediction * 1.12

print("\n------------------------------")
print(f"Location        : {resolved or loc_input or 'Unknown'}")
print(f"Predicted Price : NPR {prediction:,.0f}")
print(f"Approximately   : {fmt(prediction)}")
print(f"Price Range     : {fmt(low)}  —  {fmt(high)}")
print("------------------------------\n")
