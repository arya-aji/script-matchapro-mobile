
import csv
import os
import shutil

def update_status():
    podes_file = 'direktori_podes_checked.csv'
    usaha_file = 'direktori_usaha_checked.csv'
    output_file = 'direktori_usaha_checked_updated.csv'
    
    # 1. Load active IDs from podes file
    active_ids = set()
    print(f"Reading {podes_file}...")
    
    try:
        with open(podes_file, mode='r', encoding='utf-8', errors='replace') as f:
            # Detect header to find STATUS_UPDATE column index
            # Podes file is semicolon separated based on inspection
            reader = csv.reader(f, delimiter=';')
            header = next(reader)
            
            # clean header names (strip BOM if any, whitespace)
            header = [h.strip().replace('\ufeff', '') for h in header]
            
            try:
                idsbr_idx = 0 # Column A is IDSBR
                # Find STATUS_UPDATE column
                status_idx = -1
                for i, h in enumerate(header):
                    if 'STATUS_UPDATE' in h:
                        status_idx = i
                        break
                
                if status_idx == -1:
                    print("Error: Column 'STATUS_UPDATE' not found in podes file header.")
                    print(f"Header found: {header}")
                    print(f"Header found: {header}")
                    return
            except ValueError:
                print("Error parsing header")
                return
            for row in reader:
                if len(row) > status_idx:
                    status_val = row[status_idx].strip()
                    idsbr_val = row[idsbr_idx].strip()
                    
                    if status_val == 'AKTIF':
                        active_ids.add(idsbr_val)
                        
            print(f"Found {len(active_ids)} active IDs in podes file.")
                        
    except Exception as e:
        print(f"Error reading {podes_file}: {e}")
        return

    print(f"Found {len(active_ids)} active IDs in podes file.")

    # 2. Update usaha file
    print(f"Processing {usaha_file}...")
    updated_count = 0
    
    try:
        with open(usaha_file, mode='r', encoding='utf-8', errors='replace') as infile, \
             open(output_file, mode='w', encoding='utf-8', newline='') as outfile:
            
            # Usaha file is comma separated
            reader = csv.reader(infile, delimiter=',')
            writer = csv.writer(outfile, delimiter=',')
            
            header = next(infile)
            # Write header manually to preserve exact formatting if possible, 
            # but csv module writer is safer for structure.
            # Let's parse header with csv reader to handle quoting correctly if present in header
            # Reset seek to use csv reader for header
            infile.seek(0)
            reader = csv.reader(infile, delimiter=',')
            header_row = next(reader)
            writer.writerow(header_row)
            
            # Identify status_perusahaan index (Column N -> index 13)
            # Verify with header name "status_perusahaan"
            status_usaha_idx = 13
            idsbr_usaha_idx = 0
            
            if len(header_row) > 13 and 'status_perusahaan' in header_row[13]:
                pass # Verified
            else:
                # Try to find it
                try:
                    status_usaha_idx = header_row.index('status_perusahaan')
                except ValueError:
                    print("Warning: 'status_perusahaan' not found at index 13 or by name. Using index 13 as default per instructions.")
            
            for row in reader:
                if len(row) > status_usaha_idx:
                    idsbr = row[idsbr_usaha_idx].strip()
                    if idsbr in active_ids:
                        # Update status
                        if row[status_usaha_idx] != 'Aktif': # Only count real changes? Or just all matches?
                            # User said "isikan dengan STATUS_UPDATE" (which is 'Aktif').
                            pass
                        row[status_usaha_idx] = 'Aktif'
                        updated_count += 1
                
                writer.writerow(row)
                
        print(f"Finished. Updated {updated_count} rows.")
        print(f"Output saved to {output_file}")
        
    except Exception as e:
        print(f"Error processing {usaha_file}: {e}")

if __name__ == '__main__':
    update_status()
