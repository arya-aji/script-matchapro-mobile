import pandas as pd
import rapidfuzz
from rapidfuzz import fuzz, process
import numpy as np
import time

import argparse

# Configuration
DEFAULT_INPUT_FILE = 'direktori_usaha_full_all_columns_2026.csv'
DEFAULT_OUTPUT_FILE = 'direktori_usaha_checked.csv'
FUZZY_NAME_THRESHOLD = 85
FUZZY_ADDRESS_THRESHOLD = 80

def clean_text(text):
    if not isinstance(text, str):
        return ""
    return text.lower().strip()

def main():
    parser = argparse.ArgumentParser(description='Detect duplicate businesses.')
    parser.add_argument('input_file', nargs='?', default=DEFAULT_INPUT_FILE, help='Input CSV file')
    parser.add_argument('output_file', nargs='?', default=DEFAULT_OUTPUT_FILE, help='Output CSV file')
    args = parser.parse_args()

    print(f"Loading data from {args.input_file}...")
    try:
        # Load necessary columns for comparison + idsbr
        # We need all columns for the output
        # Load necessary columns for comparison + idsbr + spatial
        # We need to ensure lat/long are floats. "coerce" errors later or load as object first?
        # Better to load as is, then numeric conversion.
        df = pd.read_csv(args.input_file, dtype={'idsbr': str, 'kode_wilayah': str, 'kdkec': str})
        
        # Convert lat/long to numeric, forcing errors to NaN
        if 'latitude' in df.columns and 'longitude' in df.columns:
            df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
            df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
        else:
            print("Warning: 'latitude' or 'longitude' columns missing. Spatial check will be skipped.")
            df['latitude'] = np.nan
            df['longitude'] = np.nan
    except FileNotFoundError:
        print(f"Error: File {args.input_file} not found.")
        return
    
    print(f"Loaded {len(df)} records.")

    # Initialize cek_duplikat column
    df['cek_duplikat'] = False
    df['idsbr_real'] = None # Initialize idsbr_real with None (object dtype)
    
    # Preprocessing
    print("Preprocessing text columns...")
    df['nama_clean'] = df['nama_usaha'].apply(clean_text)
    df['alamat_clean'] = df['alamat_usaha'].apply(clean_text)
    
    # --- Exact Duplicates ---
    print("Checking for exact duplicates (Name + Address)...")
    # Identify duplicates based on cleaned name and address
    
    # First, sort by idsbr ascending so the first one is the smallest
    df.sort_values(by='idsbr', inplace=True)
    
    # Calculate the 'master' ID (minimum idsbr) for each group
    # We use transform which aligns with the original dataframe index
    print("Grouping for exact matches...")
    # Group by name+address
    # Note: groupBy with NaN values in keys might behave differently (but we cleaned text to "" so no NaNs in keys likely)
    master_ids = df.groupby(['nama_clean', 'alamat_clean'])['idsbr'].transform('first') # 'first' is min because we sorted
    
    # Identify which ones are duplicates
    # A row is a duplicate if its idsbr is NOT equal to the master_ids
    # (Because we rely on sort order, master_id will be the first/smallest)
    
    exact_dupes_mask = (df['idsbr'] != master_ids)
    
    df.loc[exact_dupes_mask, 'cek_duplikat'] = True
    df.loc[exact_dupes_mask, 'idsbr_real'] = master_ids[exact_dupes_mask]
    
    print(f"Found {exact_dupes_mask.sum()} exact duplicates.")


    # --- Fuzzy Duplicates ---
    print("Checking for fuzzy duplicates (Multi-Pass Blocking + Spatial)...")

    # Haversine distance function
    def haversine_distance(lat1, lon1, lat2, lon2):
        if pd.isna(lat1) or pd.isna(lon1) or pd.isna(lat2) or pd.isna(lon2):
            return float('inf')
            
        R = 6371000  # Radius of Earth in meters
        phi1 = np.radians(lat1)
        phi2 = np.radians(lat2)
        delta_phi = np.radians(lat2 - lat1)
        delta_lambda = np.radians(lon2 - lon1)

        a = np.sin(delta_phi / 2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2)**2
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

        return R * c

    # Helper function for processing blocks
    def process_block(df, subset_mask):
        subset_df = df[subset_mask]
        
        if len(subset_df) < 2:
            return 0
        
        count_found = 0
        names = subset_df['nama_clean'].tolist()
        
        try:
            dist_matrix = process.cdist(names, names, scorer=fuzz.ratio, workers=-1, dtype=np.uint8)
        except Exception:
            return 0

        rows, cols = np.where(np.triu(dist_matrix, k=1) >= FUZZY_NAME_THRESHOLD)
        
        for r_idx, c_idx in zip(rows, cols):
            Rec1 = subset_df.iloc[r_idx]
            Rec2 = subset_df.iloc[c_idx]
            
            real_idx1 = Rec1.name 
            real_idx2 = Rec2.name
            
            # Skip if both already marked
            if df.at[real_idx1, 'cek_duplikat'] and df.at[real_idx2, 'cek_duplikat']:
                 continue

            is_duplicate = False
            
            # 1. Address Text Check
            addr_score = fuzz.partial_ratio(Rec1['alamat_clean'], Rec2['alamat_clean'])
            if addr_score >= FUZZY_ADDRESS_THRESHOLD:
                is_duplicate = True
            else:
                # 2. Spatial Check (Fallback)
                # Ensure latitude/longitude are available
                try:
                    d = haversine_distance(Rec1['latitude'], Rec1['longitude'], Rec2['latitude'], Rec2['longitude'])
                    if d < 1000: # 1000 meters threshold
                        is_duplicate = True
                except Exception:
                    pass # Ignore spatial errors (e.g. invalid types)
            
            if is_duplicate:
                id1 = Rec1['idsbr']
                id2 = Rec2['idsbr']
                
                # Determine Master (smaller ID) and Dupe (larger ID)
                if id1 < id2:
                    master_idx = real_idx1
                    dupe_idx = real_idx2
                    master_id = id1
                else:
                    master_idx = real_idx2
                    dupe_idx = real_idx1
                    master_id = id2
                
                # Resolve Transitive
                if df.at[master_idx, 'cek_duplikat']:
                     proposed_master = df.at[master_idx, 'idsbr_real']
                     if pd.notna(proposed_master):
                         master_id = proposed_master
                
                # Mark Dupe
                if not df.at[dupe_idx, 'cek_duplikat']:
                    df.at[dupe_idx, 'cek_duplikat'] = True
                    df.at[dupe_idx, 'idsbr_real'] = master_id
                    count_found += 1
                else:
                    current_master = df.at[dupe_idx, 'idsbr_real']
                    if pd.notna(current_master) and (str(master_id) < str(current_master)):
                         df.at[dupe_idx, 'idsbr_real'] = master_id
                         
        return count_found

    # PASS 1: Regional Blocking (Kode Wilayah)
    print("\n--- Pass 1: Blocking by Kode Wilayah ---")
    unique_codes = df['kode_wilayah'].dropna().unique()
    total_codes = len(unique_codes)
    fuzzy_count = 0
    
    for i, code in enumerate(unique_codes):
        if i % 100 == 0:
            print(f"Pass 1: Processing Block {i}/{total_codes}...", end='\r')
        
        subset_mask = (df['kode_wilayah'] == code)
        fuzzy_count += process_block(df, subset_mask)

    # PASS 2: Name Blocking (First 3 chars of clean name)
    print("\n\n--- Pass 2: Blocking by Name Prefix (First 3 chars) ---")
    print("Generating Name Blocks...")
    pattern = r'^(pt|cv|ud|pd|toko|warung|yayasan)\.?\s+'
    df['name_block'] = df['nama_clean'].str.replace(pattern, '', regex=True).str[:3]
    
    unique_name_blocks = df['name_block'].dropna().unique()
    total_name_blocks = len(unique_name_blocks)
    
    for i, block_key in enumerate(unique_name_blocks):
        if len(str(block_key)) < 2: continue
            
        if i % 100 == 0:
            print(f"Pass 2: Processing Block {i}/{total_name_blocks}...", end='\r')
            
        subset_mask = (df['name_block'] == block_key)
        fuzzy_count += process_block(df, subset_mask)

    print(f"\nProcessing complete. Found {fuzzy_count} additional fuzzy duplicates (cumulative).")
    
    df.drop(columns=['nama_clean', 'alamat_clean', 'name_block'], inplace=True, errors='ignore')
    
    # Save
    print(f"Saving to {args.output_file}...")
    df.to_csv(args.output_file, index=False)
    print("Done.")

if __name__ == "__main__":
    main()
