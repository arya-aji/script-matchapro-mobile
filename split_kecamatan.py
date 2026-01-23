
import pandas as pd
import os
import re

def sanitize_sheet_name(name):
    """Sanitizes sheet name to be valid for Excel."""
    if not isinstance(name, str):
        name = str(name)
    # Remove invalid characters: : \ / ? * [ ]
    name = re.sub(r'[:\\/?*\[\]]', '', name)
    # Truncate to 31 characters
    return name[:31]

def split_csv_by_kecamatan():
    input_file = 'direktori_usaha_checked_updated.csv'
    output_dir = 'split_outputs'
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")
        
    print(f"Reading {input_file}...")
    try:
        # Read the csv - optimize types if needed, but standard read is usually ok for 250MB
        # Ensure nmkec and nmdesa are read as strings
        df = pd.read_csv(input_file, dtype={'nmkec': str, 'nmdesa': str})
        
        print("Grouping by Kecamatan...")
        kecamatan_groups = df.groupby('nmkec')
        
        total_kec = len(kecamatan_groups)
        print(f"Found {total_kec} Kecamatan. Starting export...")
        
        for i, (kec_name, kec_df) in enumerate(kecamatan_groups, 1):
            safe_kec_name = sanitize_sheet_name(str(kec_name).strip())
            output_path = os.path.join(output_dir, f"{safe_kec_name}.xlsx")
            
            print(f"[{i}/{total_kec}] Processing {safe_kec_name}...")
            
            try:
                with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                    desa_groups = kec_df.groupby('nmdesa')
                    for desa_name, desa_df in desa_groups:
                        safe_sheet_name = sanitize_sheet_name(str(desa_name).strip())
                        desa_df.to_excel(writer, sheet_name=safe_sheet_name, index=False)
            except Exception as e:
                print(f"Error writing {output_path}: {e}")
                
        print("All done!")
        
    except Exception as e:
        print(f"Error processing file: {e}")

if __name__ == "__main__":
    split_csv_by_kecamatan()
