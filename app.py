from flask import Flask, render_template, request, jsonify, send_from_directory
import pandas as pd
import numpy as np
import pickle
import re
from pathlib import Path
from src.location_resolver import LocationResolver

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
BUNDLE_PATH = BASE_DIR / 'model_bundle.pkl'

# ── Load model once at startup ────────────────────────────────────────────────
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
    try:
        with open(BASE_DIR / 'model_meta.pkl', 'rb') as f:
            meta = pickle.load(f)
    except FileNotFoundError:
        meta = {}

log_transformed = meta.get('log_transformed', False)
rate_maps       = meta.get('rate_maps', {})
loc_rate        = rate_maps.get('loc_rate',    {})
city_rate       = rate_maps.get('city_rate',   {})
global_rate     = rate_maps.get('global_rate', 8_000_000)
resolver_locations = meta.get('resolver_locations', [])
model_locations = sorted([
    col.replace('Location_', '')
    for col in model_columns
    if col.startswith('Location_')
])
known_locations = sorted(set([*model_locations, *resolver_locations]))
resolver = LocationResolver(model_columns, supported_locations=known_locations)

CITY_MAP = {
    'kathmandu':   'Kathmandu',
    'kathmandhu':  'Kathmandu',
    'karhmandu':   'Kathmandu',
    'lalitpur':    'Lalitpur',
    'bhaktapur':   'Bhaktapur',
    'sitapaila':   'Kathmandu',
    'narayanthan': 'Kathmandu',
}

PLACE_NAME_PATTERN = re.compile(r'^(?!.*\d).+$')


def has_valid_place_name(value):
    return bool(value) and bool(PLACE_NAME_PATTERN.match(value.strip()))

def normalize_city(city_input):
    return CITY_MAP.get(city_input.strip().lower(), city_input.strip().title())

def get_land_rates(resolved_location, city_input):
    city_norm = normalize_city(city_input)
    land_rate = (loc_rate.get(resolved_location)
                 or city_rate.get(city_norm)
                 or global_rate)
    c_rate    = city_rate.get(city_norm, global_rate)
    return float(land_rate), float(c_rate)

def fmt(val):
    # FIX: was missing fallback — values under 1L returned None → JSON crash
    if val >= 10_000_000:
        return f"{val / 10_000_000:.2f} Crore"
    if val >= 100_000:
        return f"{val / 100_000:.2f} Lakh"
    return f"NPR {val:,.0f}"

def build_input(area, bhk, bath, floors, road, resolved, city_input):
    # FIX: single input_df build — previous version built it twice, second
    # pass wiped the first and had no zero-division guards
    input_df = pd.DataFrame(0, index=[0], columns=model_columns)

    input_df['Area_Anna']     = area
    input_df['BHK']           = bhk
    input_df['Bathrooms']     = bath
    input_df['Floors']        = floors
    input_df['Road_Width_Ft'] = road

    input_df['BHK_per_Anna']  = bhk  / area   if area   > 0 else 0
    input_df['Bath_per_BHK']  = bath / bhk    if bhk    > 0 else 0
    input_df['Area_x_Floors'] = area * floors
    input_df['Road_x_Area']   = road * area

    # FIX: feed loc_land_rate and city_land_rate — without these the two most
    # important location features are always 0 and predictions ignore location
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


@app.route('/')
def index():
    return render_template('index.html', locations=known_locations)


@app.route('/images/<path:filename>')
def images(filename):
    return send_from_directory(BASE_DIR / 'images', filename)


@app.route('/predict', methods=['POST'])
def predict():
    data = request.get_json()

    loc_input  = data.get('location', '').strip()
    city_input = data.get('city', 'Kathmandu').strip()

    if not has_valid_place_name(loc_input):
        return jsonify({'error': 'Location must use text only. Numbers are not allowed.'}), 400
    if not has_valid_place_name(city_input):
        return jsonify({'error': 'City must use text only. Numbers are not allowed.'}), 400

    area       = float(data.get('area',   4))
    bhk        = int(data.get('bhk',      3))
    bath       = int(data.get('bath',      2))
    floors     = float(data.get('floors',  2))
    road       = float(data.get('road',   12))

    # Guard against bad inputs that would cause division by zero
    area   = max(area,   0.1)
    bhk    = max(bhk,    1)
    floors = max(floors, 0.5)

    result   = resolver.resolve(loc_input)
    resolved = result.get('resolved')
    note     = result.get('note')

    input_df   = build_input(area, bhk, bath, floors, road, resolved, city_input)
    raw        = float(model.predict(input_df)[0])
    prediction = float(np.exp(raw)) if log_transformed else raw
    low        = prediction * 0.88
    high       = prediction * 1.12

    return jsonify({
        'prediction':  prediction,
        'display':     fmt(prediction),
        'low':         fmt(low),
        'high':        fmt(high),
        'npr':         f"NPR {prediction:,.0f}",
        'location':    resolved or loc_input,
        'note':        note,
        'method':      result.get('method'),
        'distance_km': result.get('distance_km'),
    })


if __name__ == '__main__':
    app.run(debug=True)
