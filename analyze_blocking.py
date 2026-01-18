import pandas as pd
import re

INPUT_FILE = 'direktori_usaha_full_all_columns_2026.csv'

def clean_name_for_blocking(text):
    if not isinstance(text, str):
        return ""
    # Remove common entity types from start
    text = text.lower().strip()
    text = re.sub(r'^(pt|cv|ud|pd|toko|warung)\.?\s+', '', text)
    return text[:3]

def main():
    print(f"Loading data from {INPUT_FILE}...")
    try:
        df = pd.read_csv(INPUT_FILE, dtype=str, usecols=['kode_wilayah', 'nama_usaha'])
    except Exception as e:
        print(e)
        return

    print(f"Loaded {len(df)} records.")
    
    # Analyze kode_wilayah length
    df['kw_len'] = df['kode_wilayah'].str.len().fillna(0).astype(int)
    print("\nKode Wilayah Length Distribution:")
    print(df['kw_len'].value_counts().sort_index())
    
    # Analyze Name Blocking
    df['name_block'] = df['nama_usaha'].apply(clean_name_for_blocking)
    block_counts = df['name_block'].value_counts()
    
    print("\nTop 10 Largest Name Blocks (First 3 chars):")
    print(block_counts.head(10))
    print("\nName Block Size Stats:")
    print(block_counts.describe())

if __name__ == "__main__":
    main()
