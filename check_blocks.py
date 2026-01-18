import pandas as pd

# Configuration
INPUT_FILE = 'direktori_usaha_full_all_columns_2026.csv'

def main():
    print(f"Loading data from {INPUT_FILE}...")
    try:
        df = pd.read_csv(INPUT_FILE, dtype={'kode_wilayah': str}, usecols=['kode_wilayah'])
    except FileNotFoundError:
        print(f"Error: File {INPUT_FILE} not found.")
        return

    print(f"Loaded {len(df)} records.")
    
    counts = df['kode_wilayah'].value_counts()
    print("\nTop 10 largest blocks:")
    print(counts.head(10))
    print("\nStats:")
    print(counts.describe())

if __name__ == "__main__":
    main()
