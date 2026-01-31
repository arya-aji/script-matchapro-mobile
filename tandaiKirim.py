
import pandas as pd
import time
import sys
import json
import re
import random
import threading
import requests
from playwright.sync_api import sync_playwright
from login import login_with_sso, user_agents

version = "1.3.4"


class MatchaSender:
    def __init__(self, username, password, otp_code=None, config=None, logger_callback=None, vpn_callback=None, result_queue=None):
        self.username = username
        self.password = password
        self.otp_code = otp_code
        self.config = config or {}
        self.logger_callback = logger_callback
        self.vpn_callback = vpn_callback
        self.result_queue = result_queue
        self.worker_id = 0

        self.total_workers = 1
        self.running = True
        
        # Config defaults
        self.base_delay = self.config.get('base_delay', 15)
        self.use_random = self.config.get('use_random', True)
        self.csv_path = self.config.get('csv_path', 'data_gc_profiling_kirim.csv')
        self.row_start = int(self.config.get('row_start', 0))
        self.timeout_min = int(self.config.get('timeout_min', 30))
        self.timeout_max = int(self.config.get('timeout_max', 30))
        self.headless = self.config.get('headless', False)

    def log(self, message):
        prefix = f"[User: {self.username}] " if self.total_workers > 1 else ""
        full_msg = f"{prefix}{message}"
        
        if self.logger_callback:
            self.logger_callback(full_msg)
            
        # Also print to console with timestamp
        from datetime import datetime
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {full_msg}")

    def check_connection(self):
        url = "https://matchapro.web.bps.go.id"
        try:
            requests.get(url, timeout=10)
            return True
        except:
            return False

    def extract_tokens(self, page):
        # Tunggu hingga tag meta token CSRF terpasang
        page.wait_for_selector('meta[name="csrf-token"]', state='attached', timeout=10000)

        # Ekstrak _token dari halaman (token CSRF dari tag meta)
        token_element = page.locator('meta[name="csrf-token"]')
        if token_element.count() > 0:
            _token = token_element.get_attribute('content')
        else:
            raise Exception("Gagal mengekstrak _token - tag meta tidak ditemukan")

        # Ekstrak gc_token dari konten halaman
        content = page.content()
        # Mencoba mencocokkan 'let gcSubmitToken' dengan kutip satu atau dua dan spasi fleksibel
        match = re.search(r"let\s+gcSubmitToken\s*=\s*(['\"])([^'\"]+)\1", content)
        if match:
            gc_token = match.group(2)
        else:
             # Analisa konten error
            if "Akses lewat matchapro mobile aja" in content or "Not Authorized" in content:
                self.log("❌ ERROR FATAL: AKES DITOLAK SERVER (Deteksi Desktop)")
            
            raise Exception("gc_token tidak ditemukan (Cek pesan error di atas)")
        
        return _token, gc_token

    def run_worker(self, worker_id, total_workers):
        self.worker_id = worker_id
        self.total_workers = total_workers
        
        pw = None
        browser = None
        
        try:
            # Check Version & MOTD only on first worker to avoid spam


            # --- VPN PRE-CHECK ---
            if self.vpn_callback:
                if not self.check_connection():
                    self.log("⚠️ Koneksi/VPN Off. Mencoba Reconnect sebelum login...")
                    self.vpn_callback()
                    
                    # Wait loop
                    for _ in range(12): # Wait up to 60s
                        time.sleep(5)
                        self.log("Menunggu koneksi...")
                        if self.check_connection():
                            self.log("✅ Koneksi Stabil.")
                            break
                    else:
                        self.log("❌ Gagal Reconnect VPN. Melanjutkan dengan risiko...")
            # ---------------------

            # Start private Playwright instance
            pw = sync_playwright().start()
            
            self.log("Sedang mencoba login...")
            
            # Retry Login Loop
            while self.running:
                page, browser = login_with_sso(self.username, self.password, self.otp_code, headless=self.headless, playwright_instance=pw)
                
                if page:
                    break
                
                self.log("Login Gagal! Mencoba lagi dalam 10 detik...")
                time.sleep(10)
            
            if not page:
                self.log("Gagal login setelah retry atau dihentikan.")
                return False

            self.log(f"Login Berhasil. Memulai proses (Worker {worker_id+1}/{total_workers})...")

             # Navigasi ke /dirgc
            url_gc = "https://matchapro.web.bps.go.id/dirgc"
            page.goto(url_gc)
            page.wait_for_load_state('networkidle')

            # Ekstrak tokens
            _token, gc_token = self.extract_tokens(page)
            # self.log(f"Token Initialized.")

            url_post = "https://matchapro.web.bps.go.id/dirgc/konfirmasi-user"
            
            # Load Data
            df = self.load_csv(self.csv_path)
            self.log(f"Total data CSV: {len(df)} baris")

            # Process Loop
            for index in range(len(df)):
                if not self.running:
                    self.log("Stopping worker...")
                    break

                # Skip rows before start
                if index < self.row_start:
                    continue

                # Partition work: Only process rows belonging to this worker
                if index % self.total_workers != self.worker_id:
                    continue

                row = df.iloc[index]
                gc_token, skipped = self.process_row(index, row, page, url_post, _token, gc_token)
                
                if skipped:
                    continue # Skip delay

                # Wait
                sleep_val = float(self.base_delay)
                if self.use_random:
                    sleep_val += random.uniform(0, 5)
                
                # self.log(f"Sleeping {sleep_val:.1f}s...")
                time.sleep(sleep_val)

            self.log("Semua tugas selesai.")

        except Exception as e:
            self.log(f"Worker Error: {e}")
        finally:
            if browser:
                browser.close()
            if pw:
                pw.stop()

    def process_row(self, index, row, page, url, _token, gc_token):
        # returns (gc_token, skipped_boolean)
        
        perusahaan_id = row['perusahaan_id']
        latitude = row['latitude']
        longitude = row['longitude']
        hasilgc = row['hasilgc']
        
        # Custom Skip Logic: gc_username exists
        if 'gc_username' in row:
             gc_user = row['gc_username']
             if pd.notna(gc_user) and str(gc_user).strip() != '' and str(gc_user).strip().lower() != 'nan':
                 self.log(f"Skip Row {index}: gc_username terisi ({gc_user})")
                 return gc_token, True

        # Sanitize hasilgc (Handle NaN -> 99)
        if pd.isna(hasilgc) or str(hasilgc).strip() == '':
            hasilgc = 99

        # Validation checks... reuse logic
        # Convert to int safe check
        try:
            hasilgc_int = int(float(hasilgc))
            if hasilgc_int not in [99, 1, 3, 4, 55]:
                self.log(f"Skip Row {index}: hasilgc invalid ({hasilgc})")
                return gc_token, True
            hasilgc = hasilgc_int # Use clean int
        except:
             self.log(f"Skip Row {index}: hasilgc invalid format ({hasilgc})")
             return gc_token, True # Skipped

        if hasilgc == 1:
             if pd.isna(latitude) or pd.isna(longitude):
                 self.log(f"Skip Row {index}: Lat/Long empty for hasilgc=1")
                 return gc_token, True # Skipped

        max_retries = 5
        consecutive_429 = 0
        
        for attempt in range(max_retries):
            try:
                # Sanitize Coordinates
                lat_clean = str(latitude).replace(',', '.')
                long_clean = str(longitude).replace(',', '.')
                
                # Get Edit Columns
                nama_usaha_edit = row.get('nama_usaha_edit', '')
                alamat_usaha_edit = row.get('alamat_usaha_edit', '')

                form_data = {
                    "perusahaan_id": str(perusahaan_id),
                    "latitude": lat_clean,
                    "longitude": long_clean,
                    "hasilgc": str(hasilgc),
                    "gc_token": gc_token,
                    "_token": _token
                }
                
                # Add optional edit fields if they exist
                if pd.notna(nama_usaha_edit) and str(nama_usaha_edit).strip():
                    form_data["nama_usaha"] = str(nama_usaha_edit).strip()
                    
                if pd.notna(alamat_usaha_edit) and str(alamat_usaha_edit).strip():
                    form_data["alamat_usaha"] = str(alamat_usaha_edit).strip()
                
                post_headers = {
                    "origin": "https://matchapro.web.bps.go.id",
                    "referer": "https://matchapro.web.bps.go.id/dirgc"
                }

                # Randomize timeout
                current_timeout = random.randint(self.timeout_min, self.timeout_max) * 1000
                
                response = page.request.post(url, form=form_data, headers=post_headers, timeout=current_timeout, fail_on_status_code=False)
                status = response.status
                text = response.text()
                
                if status == 429:
                    consecutive_429 += 1
                    wait = random.randint(30, 60) if consecutive_429 == 1 else 600
                    self.log(f"Rate Limit (429) hit. Waiting {wait}s...")
                    time.sleep(wait)
                    
                    # Refresh tokens
                    page.reload()
                    page.wait_for_load_state('networkidle')
                    _token, gc_token = self.extract_tokens(page)
                    continue

                    return gc_token, False

                if status == 200:
                    try:
                        resp_json = response.json()
                        if 'new_gc_token' in resp_json:
                            gc_token = resp_json['new_gc_token']
                    except:
                        pass
                    
                    self.log(f"Row {index}: Success (200) - {text[:50]}...")
                    
                    # Update Result (gc_username)
                    if self.result_queue:
                        try:
                            self.result_queue.put({'index': index, 'username': self.username})
                        except: pass

                    # Update baris.txt logic (Thread-safe-ish check)
                    try:
                        current_saved = 0
                        try:
                            with open('baris.txt', 'r') as f:
                                current_saved = int(f.read().strip())
                        except:
                            pass
                        
                        if index > current_saved:
                            with open('baris.txt', 'w') as f:
                                f.write(str(index))
                    except Exception as e:
                        print(f"Failed to update baris.txt: {e}")
                    
                    return gc_token, False

                # Handle other retryable errors (400 token invalid, 503)
                retry = False
                if status in [400, 503]:
                    # Check message content for specific retryable errors
                    if "Token invalid" in text or "Server sedang sibuk" in text:
                        retry = True
                
                if retry:
                    self.log(f"Retryable error {status} for row {index}. Refreshing tokens...")
                    page.reload()
                    page.wait_for_load_state('networkidle')
                    _token, gc_token = self.extract_tokens(page)
                    time.sleep(5)
                    continue
                
                # If we get here, it's a non-retryable error or failed retry
                self.log(f"Row {index}: Failed ({status}) - {text}")
                # Log to error.txt
                with open('error.txt', 'a') as f:
                     f.write(f"Row {index} [User:{self.username}]: {status} - {text} | Payload: {form_data}\n")
                return gc_token, False

            except Exception as e:
                error_msg = str(e).lower()
                is_network_error = any(x in error_msg for x in ['timeout', 'connection', 'network', 'socket', 'reset', 'refused'])
                
                self.log(f"Request Error Row {index}: {e}")
                
                if is_network_error and self.vpn_callback:
                    self.log("⚠️ Triggering VPN Callback...")
                    self.vpn_callback()
                    self.log("Waiting 20s for network/VPN recovery...")
                    time.sleep(20)
                else:
                    time.sleep(5)
        
        return gc_token, False

    def load_csv(self, path):
        # Support Excel
        if path.lower().endswith(('.xlsx', '.xls')):
            try:
                # Engine 'openpyxl' is default for xlsx in recent pandas
                return pd.read_excel(path)
            except Exception as e:
                self.log(f"Gagal baca Excel: {e}")
                # Fallthrough to try CSV just in case
        
        # Smart load logic for CSV
        encodings = ['utf-8', 'cp1252', 'latin1']
        seps = [';', ',', '\t']
        
        for enc in encodings:
            for sep in seps:
                try:
                    df = pd.read_csv(path, encoding=enc, sep=sep, nrows=2)
                    if 'perusahaan_id' in df.columns:
                        return pd.read_csv(path, encoding=enc, sep=sep)
                except:
                    continue
        
        # Fallback
        return pd.read_csv(path, sep=';', encoding='latin1') # Last resort assumption



    def stop(self):
        self.running = False


# Legacy Wrapper for CLI
def main(username=None, password=None, otp_code=None, row_start=None, csv_path=None, logger_callback=None, base_delay=15, use_random=True):
    config = {
        'row_start': row_start or 0,
        'csv_path': csv_path,
        'base_delay': base_delay,
        'use_random': use_random
    }
    
    sender = MatchaSender(username, password, otp_code, config, logger_callback, vpn_callback=None)
    # Run in main thread directly
    sender.run_worker(0, 1)
    return True

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        main(sys.argv[1], sys.argv[2])
    else:
        main()
