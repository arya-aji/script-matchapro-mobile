import pandas as pd
import os

input_file = r'd:\Sync\gitHub\script-matchapro-mobile\direktori_usaha_checked.xlsx'
output_file = r'd:\Sync\gitHub\script-matchapro-mobile\data_jakpus_all.csv'

print(f"Reading {input_file}...")
try:
    df = pd.read_excel(input_file)
except Exception as e:
    print(f"Error reading file: {e}")
    exit(1)

print("Cols:", df.columns)

if 'cek_duplikat' in df.columns:
    print(f"Unique values in cek_duplikat before filter: {df['cek_duplikat'].unique()}")
    
    # Filter for True (boolean or string 'TRUE')
    # Converting to string and upper case to handle "True", "TRUE", True, etc.
    # Also handle 1.0 if it was parsed as float
    def is_true(x):
        s = str(x).upper()
        return s == 'TRUE' or s == '1' or s == '1.0'

    filtered_df = df[df['cek_duplikat'].apply(is_true)].copy()
    
    print(f"Rows after filtering: {len(filtered_df)}")
    
    print("Adding 'hasilgc' = 4...")
    filtered_df['hasilgc'] = 4
    
    print(f"Saving to {output_file}...")
    filtered_df.to_csv(output_file, index=False)
    print("Done.")

else:
    print("Error: Column 'cek_duplikat' not found in the excel file.")
