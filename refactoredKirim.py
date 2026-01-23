import requests
import pandas as pd
import time
import sys
import json
import re
import argparse
import math
import os
from concurrent.futures import ProcessPoolExecutor
from playwright.sync_api import sync_playwright

# Import login function and user agents
# Assuming login.py is in the same directory
try:
    from login import login_with_sso, user_agents
except ImportError:
    print("Error: Could not import 'login.py'. Make sure it exists in the same directory.")
    sys.exit(1)

VERSION = "1.2.4"
MOTD_URL = "https://dev.ketut.web.id/TGlrZWxpaG9vZA.txt"
VERSION_URL = "https://dev.ketut.web.id/ver.txt"
GC_URL = "https://matchapro.web.bps.go.id/dirgc"
POST_URL = "https://matchapro.web.bps.go.id/dirgc/konfirmasi-user"

def check_app_version():
    """Checks the remote version against the local version."""
    try:
        response = requests.get(VERSION_URL, timeout=10)
        if response.status_code == 200:
            remote_version = response.text.strip()
            if remote_version != VERSION:
                print(f"Versi saat ini: {VERSION}")
                print(f"Versi terbaru: {remote_version}")
                print("Gunakan versi terbaru. Silakan unduh dari:")
                print("https://github.com/ketut/SsscriptGC")
                time.sleep(5)
                sys.exit(1)
        else:
            print("Gagal mengambil versi terbaru. Melanjutkan...")
    except Exception as e:
        print(f"Gagal mengecek versi: {e}. Melanjutkan...")

def check_motd():
    """Checks and displays Message of the Day."""
    try:
        motd_response = requests.get(MOTD_URL, timeout=10)
        if motd_response.status_code == 200:
            motd_data = motd_response.json()
            if motd_data.get("motd") == 1:
                print(motd_data.get("message", ""))
    except Exception as e:
        pass

def extract_tokens(page):
    """Extracts CSRF token (_token) and GC token (gc_token) from the page."""
    # Tunggu hingga tag meta token CSRF terpasang
    try:
        page.wait_for_selector('meta[name="csrf-token"]', state='attached', timeout=10000)
    except Exception:
        pass # Try converting whatever we have

    # Ekstrak _token dari halaman (token CSRF dari tag meta)
    token_element = page.locator('meta[name="csrf-token"]')
    if token_element.count() > 0:
        _token = token_element.get_attribute('content')
    else:
        # Fallback logic can go here if needed, but usually this is fatal for CSRF
        _token = None
        # Don't raise immediately, try to find gc_token to see if it's a diff error

    # Ekstrak gc_token dari konten halaman
    content = page.content()
    # Mencoba mencocokkan 'let gcSubmitToken' dengan kutip satu atau dua dan spasi fleksibel
    match = re.search(r"let\s+gcSubmitToken\s*=\s*(['\"])([^'\"]+)\1", content)
    
    gc_token = None
    if match:
        gc_token = match.group(2)
    
    if not _token or not gc_token:
        # Analisa konten error
        if "Akses lewat matchapro mobile aja" in content or "Not Authorized" in content:
            print("\n" + "="*50)
            print("❌ ERROR FATAL: AKES DITOLAK SERVER")
            print("Penyebab: Laptop ini terdeteksi sebagai Desktop, bukan Mobile.")
            print("SOLUSI: Pastikan file 'login.py' di laptop ini SUDAH DIPERBARUI")
            print("="*50 + "\n")
        
        # Simpan konten halaman untuk debugging
        try:
            with open(f"debug_page_content_{int(time.time())}.html", "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass
            
        raise Exception(f"Gagal mengekstrak token. _token found: {bool(_token)}, gc_token found: {bool(gc_token)}")
    
    return _token, gc_token

def get_session_state(username, password, otp_code, headless=False):
    """Logins and returns the storage state (cookies, etc)."""
    print(f"Mencoba login sebagai {username}...")
    page, browser = login_with_sso(username, password, otp_code, headless=headless)
    if page:
        # Validasi mobile mode
        ua = page.evaluate("navigator.userAgent")
        print(f"[INFO] Browser User Agent: {ua}")
        
        state = page.context.storage_state()
        browser.close()
        return state
    return None

def process_row(page, row, index, gc_token, _token):
    """Processes a single row of data."""
    perusahaan_id = row['perusahaan_id']
    latitude = row['latitude']
    longitude = row['longitude']
    hasilgc = row['hasilgc']

    # Validation
    if pd.isna(hasilgc) or str(hasilgc).strip() == '' or int(hasilgc) not in [99, 1, 3, 4]:
        print(f"Skipping Row {index}: hasilgc invalid ({hasilgc})")
        return False, gc_token, _token # Continue but fail this row

    if int(hasilgc) == 1:
        if pd.isna(latitude) or str(latitude).strip() == '' or pd.isna(longitude) or str(longitude).strip() == '':
             print(f"Skipping Row {index}: Lat/Long incomplete for hasilgc=1")
             return False, gc_token, _token

    max_request_retries = 5
    
    for request_attempt in range(max_request_retries):
        try:
            form_data = {
                "perusahaan_id": str(perusahaan_id),
                "latitude": str(latitude),
                "longitude": str(longitude),
                "hasilgc": str(int(hasilgc)),
                "gc_token": gc_token,
                "_token": _token
            }
            
            post_headers = {
                "origin": "https://matchapro.web.bps.go.id",
                "referer": "https://matchapro.web.bps.go.id/dirgc"
            }

            response = page.request.post(POST_URL, form=form_data, headers=post_headers, timeout=30000)
            status_code = response.status
            response_text = response.text()
            
            # 429 Handling
            if status_code == 429:
                resp_json = {}
                try:
                    resp_json = response.json()
                except:
                    pass
                
                retry_after = resp_json.get('retry_after', 600)
                message = resp_json.get('message', 'Terlalu banyak permintaan.')
                
                # Extract time from message
                wait_time = retry_after
                time_match = re.search(r'(\d+)\s*(menit|detik|jam)', message.lower())
                if time_match:
                    val = int(time_match.group(1))
                    unit = time_match.group(2)
                    if unit == 'menit': wait_time = val * 60
                    elif unit == 'jam': wait_time = val * 3600
                    else: wait_time = val
                
                wait_time += 10 # Buffer
                print(f"❌ [Row {index}] STATUS 429. Menunggu {wait_time}s...")
                time.sleep(wait_time)
                
                # Refresh tokens
                page.reload()
                page.wait_for_load_state('networkidle')
                _token, gc_token = extract_tokens(page)
                continue

            # Token/Server Errors Retry Logic
            is_retryable = False
            if status_code in [400, 503]:
                if "Token invalid" in response_text or "Server sedang sibuk" in response_text:
                    is_retryable = True
            
            if is_retryable:
                 if request_attempt < max_request_retries - 1:
                    print(f"⚠ [Row {index}] Token/Server error. Refreshing tokens...")
                    page.reload()
                    page.wait_for_load_state('networkidle')
                    _token, gc_token = extract_tokens(page)
                    time.sleep(2)
                    continue
            
            # Network Errors are caught by Exception
            
            # Successful or Non-Retryable Error
            print(f"✅ [Row {index}] Status {status_code}: {response_text[:100]}...")
            
            # Update gc_token if provided in response
            if status_code == 200:
                try:
                    resp_json = response.json()
                    if 'new_gc_token' in resp_json:
                        gc_token = resp_json['new_gc_token']
                except:
                    pass
            
            # Logging errors
            if status_code != 200 or '"status":"error"' in response_text.lower():
                 if "Usaha ini sudah diground check" not in response_text: # Ignore generic already checked
                    try:
                        with open("error.txt", "a") as f:
                            f.write(f"Row {index}: Status {status_code} - {response_text}\n")
                    except:
                        pass

            return True, gc_token, _token

        except Exception as e:
            error_msg = str(e).lower()
            if any(x in error_msg for x in ["timeout", "reset", "refused", "aborted", "network", "socket"]):
                if request_attempt < max_request_retries - 1:
                    print(f"⚠ [Row {index}] Network error: {e}. Retrying...")
                    time.sleep(5)
                    continue
            print(f"❌ [Row {index}] Error Fatal: {e}")
            break
            
    return False, gc_token, _token

def worker_task(worker_id, chunk_data, storage_state, headless):
    """Function executed by each worker process."""
    print(f"Worker {worker_id} started. Processing {len(chunk_data)} rows.")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        
        # Replicate mobile context settings from login.py
        context = browser.new_context(
            storage_state=storage_state,
            user_agent=user_agents,
            viewport={"width": 412, "height": 915},
            is_mobile=True,
            has_touch=True,
            extra_http_headers={
                "x-requested-with": "com.matchapro.app",
                "sec-ch-ua": "\"Android WebView\";v=\"143\", \"Chromium\";v=\"143\", \"Not A(Brand\";v=\"24\"",
                "sec-ch-ua-mobile": "?1",
                "sec-ch-ua-platform": "\"Android\""
            }
        )
        
        page = context.new_page()
        
        # Add init script (important for detection)
        page.add_init_script("""
            Object.defineProperty(navigator, 'platform', {
                get: function() { return 'Linux armv8l'; }
            });
            Object.defineProperty(navigator, 'maxTouchPoints', {
                get: function() { return 5; }
            });
        """)
        
        try:
            page.goto(GC_URL)
            page.wait_for_load_state('networkidle')
            
            _token, gc_token = extract_tokens(page)
            print(f"Worker {worker_id} tokens extracted.")
            
            for i, (_, row) in enumerate(chunk_data.iterrows()):
                real_index = row.name # Original index from DataFrame
                success, gc_token, _token = process_row(page, row, real_index, gc_token, _token)
                
                # Sleep to avoid rate limits (distributed across workers?)
                # If we have 4 workers, and each sleeps 15s, we hit 4 times per 15s = 16 hits/min ~ 1 hit/3.75s
                time.sleep(15) 
                
        except Exception as e:
            print(f"Worker {worker_id} crashed: {e}")
        finally:
            browser.close()
            print(f"Worker {worker_id} finished.")

def load_data(csv_path):
    encodings = ['utf-8', 'cp1252', 'latin1']
    for enc in encodings:
        try:
            return pd.read_csv(csv_path, encoding=enc, sep=';')
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"Error reading CSV: {e}")
            sys.exit(1)
    print("Gagal membaca CSV dengan encoding apapun.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Script Matchapro Mobile Automated")
    parser.add_argument("username", help="SSO Username")
    parser.add_argument("password", help="SSO Password")
    parser.add_argument("otp", nargs="?", help="OTP Code (optional)")
    parser.add_argument("start_index", nargs="?", type=int, help="Start Index (optional)")
    
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel workers")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    
    args = parser.parse_args()
    
    check_app_version()
    check_motd()
    
    # Determine start index
    start_index = args.start_index
    if start_index is None:
        try:
            with open('baris.txt', 'r') as f:
                start_index = int(f.read().strip())
        except:
            start_index = 0
            
    print(f"--- Configuration ---")
    print(f"Username: {args.username}")
    print(f"Start Index: {start_index}")
    print(f"Workers: {args.workers}")
    print(f"Headless: {args.headless}")
    print(f"---------------------")

    # 1. Login Logic
    storage_state = get_session_state(args.username, args.password, args.otp, headless=args.headless)
    if not storage_state:
        print("Login Gagal. Keluar.")
        sys.exit(1)
        
    # 2. Load Data
    df = load_data('data_gc_profiling_kirim.csv')
    
    # 3. Slice Data
    if start_index >= len(df):
        print("Semua data sudah diproses.")
        sys.exit(0)
        
    df_to_process = df.iloc[start_index:]
    
    # 4. Split for Workers
    num_workers = min(args.workers, len(df_to_process))
    chunk_size = math.ceil(len(df_to_process) / num_workers)
    
    chunks = []
    for i in range(num_workers):
        start = i * chunk_size
        end = start + chunk_size
        chunk = df_to_process.iloc[start:end]
        if not chunk.empty:
            chunks.append(chunk)

    print(f"Memulai {len(chunks)} workers...")
    
    # 5. Execute Workers
    # Note: We must use a context manager for executor
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        for i, chunk in enumerate(chunks):
            # Pass storage_state (dict) which is pickleable
            futures.append(executor.submit(worker_task, i+1, chunk, storage_state, args.headless))
            
        # Wait for all
        for future in futures:
            try:
                future.result()
            except Exception as e:
                print(f"Main Process caught exception from worker: {e}")

    print("Semua task selesai.")

if __name__ == "__main__":
    main()
