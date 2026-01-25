import os
import pandas as pd
import glob

source_dir = 'split_outputs'
output_file = 'data_jakpus.csv'

# Get all xlsx files
files = glob.glob(os.path.join(source_dir, '*.xlsx'))
print(f"Found {len(files)} files to process.")

dfs = []
for file in files:
    print(f"Reading {file}...")
    try:
        df = pd.read_excel(file)
        dfs.append(df)
    except Exception as e:
        print(f"Error reading {file}: {e}")

if dfs:
    print("Concatenating...")
    combined_df = pd.concat(dfs, ignore_index=True)
    print(f"Saving to {output_file}...")
    combined_df.to_csv(output_file, index=False)
    print(f"Done! Saved {len(combined_df)} rows to {output_file}")
else:
    print("No data found.")
