import pandas as pd
import numpy as np
import pickle
from pathlib import Path
from sklearn.model_selection import KFold, cross_val_score, train_test_split
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / 'data' / 'nepal_house_data.csv'
BUNDLE_PATH = BASE_DIR / 'model_bundle.pkl'
RARE_THRESHOLD = 10
RATE_SUPPORT_THRESHOLD = 3
RATE_SMOOTHING = 5

# ── 1. Load data ──────────────────────────────────────────────────────────────
data = pd.read_csv(DATA_PATH)
print(f"Loaded {len(data)} rows")

# ── 2. Clean outliers ─────────────────────────────────────────────────────────
data = data[data['Bathrooms'] <= data['BHK'] + 3]
q_low  = data['Price_NPR'].quantile(0.01)
q_high = data['Price_NPR'].quantile(0.99)
data   = data[(data['Price_NPR'] >= q_low) & (data['Price_NPR'] <= q_high)]
print(f"After cleaning: {len(data)} rows")

# ── 3. Normalise City casing ──────────────────────────────────────────────────
CITY_MAP = {
    'kathmandu':   'Kathmandu',
    'kathmandhu':  'Kathmandu',
    'karhmandu':   'Kathmandu',
    'imadol':      'Lalitpur',
    'lalitpur':    'Lalitpur',
    'bhaktapur':   'Bhaktapur',
    'sitapaila':   'Kathmandu',
    'narayanthan': 'Kathmandu',
    'rumba chowk': 'Kathmandu',
}
data['City'] = data['City'].apply(
    lambda x: CITY_MAP.get(str(x).strip().lower(), str(x).strip().title())
              if pd.notna(x) else 'Other'
)
data['Raw_Location'] = data['Location'].apply(
    lambda x: str(x).strip().title() if pd.notna(x) and str(x).strip() else 'Other'
)

# ── 4. Group rare locations → 'Other' ────────────────────────────────────────
loc_counts = data['Raw_Location'].value_counts()
rare_locs  = loc_counts[loc_counts < RARE_THRESHOLD].index
data['Location'] = data['Raw_Location'].apply(
    lambda x: 'Other' if x in rare_locs else x
)
print(f"Locations after grouping: {data['Location'].nunique()} (was 370)")

# ── 5. Location land rate feature ────────────────────────────────────────────
# Teaches the model "land in Naxal costs X/anna, Thankot costs Y/anna"
# Without this, location columns are near-zero importance
data['price_per_anna_raw'] = data['Price_NPR'] / data['Area_Anna']

# Remove per-anna outliers (e.g. Mahalaxmisthan at 1000L/anna is a data error)
ppa_q99 = data['price_per_anna_raw'].quantile(0.99)
data = data[data['price_per_anna_raw'] <= ppa_q99]

loc_rate    = data.groupby('Location')['price_per_anna_raw'].median()
city_rate   = data.groupby('City')['price_per_anna_raw'].median()
global_rate = data['price_per_anna_raw'].median()

# Preserve raw-location pricing for places like Baneshwor even if they are too
# sparse for one-hot encoding, but smooth low-count areas back toward city rate.
raw_loc_counts = data['Raw_Location'].value_counts()
raw_loc_rate   = data.groupby('Raw_Location')['price_per_anna_raw'].median()
raw_loc_city   = data.groupby('Raw_Location')['City'].agg(
    lambda s: s.mode().iloc[0] if not s.mode().empty else 'Other'
)
smoothed_loc_rate = {}
for loc, rate in raw_loc_rate.items():
    loc_count = int(raw_loc_counts.get(loc, 0))
    loc_city_name = raw_loc_city.get(loc, 'Other')
    prior_rate = float(city_rate.get(loc_city_name, global_rate))
    smoothed_loc_rate[loc] = float(
        ((loc_count * float(rate)) + (RATE_SMOOTHING * prior_rate))
        / (loc_count + RATE_SMOOTHING)
    )

# Unknown locations fall back to city rate, then global median
data['loc_land_rate']  = data['Raw_Location'].map(smoothed_loc_rate).fillna(
                         data['City'].map(city_rate)).fillna(global_rate)
data['city_land_rate'] = data['City'].map(city_rate).fillna(global_rate)

print(f"After per-anna outlier removal: {len(data)} rows")

# ── 6. Feature engineering ────────────────────────────────────────────────────
data['BHK_per_Anna']  = data['BHK']       / data['Area_Anna']
data['Bath_per_BHK']  = data['Bathrooms'] / data['BHK']
data['Area_x_Floors'] = data['Area_Anna'] * data['Floors']
data['Road_x_Area']   = data['Road_Width_Ft'] * data['Area_Anna']

# ── 7. Log-transform price ────────────────────────────────────────────────────
data['Log_Price'] = np.log(data['Price_NPR'])

# ── 8. Encode categoricals ────────────────────────────────────────────────────
data_encoded = pd.get_dummies(data, columns=['Location', 'City'])

# ── 9. Features & target ──────────────────────────────────────────────────────
drop_cols = ['Price_NPR', 'Log_Price', 'District', 'price_per_anna_raw', 'Raw_Location']
X = data_encoded.drop(columns=[c for c in drop_cols if c in data_encoded.columns])
y = data['Log_Price']

print(f"Feature count: {X.shape[1]}")

# ── 10. Train / holdout split ─────────────────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)
print(f"Train: {len(X_train)} rows | Holdout: {len(X_test)} rows")

# ── 11. Prepare columns + metadata ───────────────────────────────────────────
model_columns = list(X.columns)
meta = {
    'log_transformed': True,
    'rate_maps': {
        'loc_rate':    smoothed_loc_rate,
        'city_rate':   city_rate.to_dict(),
        'global_rate': global_rate,
    },
    'resolver_locations': sorted(
        loc for loc, count in raw_loc_counts.items()
        if loc != 'Other' and int(count) >= RATE_SUPPORT_THRESHOLD
    ),
}

# ── 12. Model ─────────────────────────────────────────────────────────────────
model = GradientBoostingRegressor(
    n_estimators=500,
    learning_rate=0.03,
    max_depth=4,
    max_features=0.6,
    subsample=0.8,
    random_state=42
)

# ── 13. Cross validation ──────────────────────────────────────────────────────
kf    = KFold(n_splits=5, shuffle=True, random_state=42)
cv_r2 = cross_val_score(model, X_train, y_train, cv=kf, scoring='r2')
print(f"\n--- K-FOLD CROSS VALIDATION (train set, 5 folds) ---")
print(f"R2 per fold : {[round(s, 3) for s in cv_r2]}")
print(f"R2 mean     : {cv_r2.mean():.3f}  +-  {cv_r2.std():.3f}")

# ── 14. Fit + holdout eval ────────────────────────────────────────────────────
model.fit(X_train, y_train)

y_pred   = np.exp(model.predict(X_test))
y_actual = np.exp(y_test.values)
mae = mean_absolute_error(y_actual, y_pred)
r2  = r2_score(y_actual, y_pred)

print(f"\n--- HOLDOUT EVALUATION (unseen data) ---")
print(f"Average Error (MAE) : NPR {mae:,.0f}")
print(f"Accuracy (R2 Score) : {r2:.3f}")

# ── 15. Feature importance ────────────────────────────────────────────────────
importance = pd.Series(model.feature_importances_, index=X.columns)
top = importance.sort_values(ascending=False).head(10)
print(f"\nTop 10 Most Important Features:")
print(top.to_string())

# ── 16. Refit on all data for saved model ────────────────────────────────────
model.fit(X, y)

# Save one atomic bundle first so runtime code never sees mismatched artifacts.
with open(BUNDLE_PATH.with_suffix('.tmp'), 'wb') as f:
    pickle.dump({
        'model': model,
        'model_columns': model_columns,
        'meta': meta,
    }, f)
BUNDLE_PATH.with_suffix('.tmp').replace(BUNDLE_PATH)

with open(BASE_DIR / 'house_model.pkl', 'wb') as f:
    pickle.dump(model, f)
with open(BASE_DIR / 'model_columns.pkl', 'wb') as f:
    pickle.dump(model_columns, f)
with open(BASE_DIR / 'model_meta.pkl', 'wb') as f:
    pickle.dump(meta, f)

print("\nModel saved as 'house_model.pkl'")
