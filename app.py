import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import sys
import os
import json
import queue

# --- FIX: Set Playwright Browsers Path for PyInstaller ---
target_browsers_path = os.path.join(os.getenv('LOCALAPPDATA'), 'ms-playwright')
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = target_browsers_path
# --------------------------------------------------------

import tandaiKirim
from tandaiKirim import version, MatchaSender

# ------------------------------------------------------------------
# EMBEDDED SCRAPING LOGIC
# ------------------------------------------------------------------
import requests
import re
import csv
import concurrent.futures
from login import login_with_sso

class MatchaScraper:
    def __init__(self, logger=None):
        self.logger = logger
        self.session = requests.Session()
        self.HEADERS = {
            "host": "matchapro.web.bps.go.id",
            "connection": "keep-alive",
            "sec-ch-ua": "\"Android WebView\";v=\"143\", \"Chromium\";v=\"143\", \"Not A(Brand\";v=\"24\"",
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": "\"Android\"",
            "x-requested-with": "com.matchapro.app",
            "user-agent": "Mozilla/5.0 (Linux; Android 12; M2010J19CG Build/SKQ1.211202.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/143.0.7499.192 Mobile Safari/537.36",
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": "https://matchapro.web.bps.go.id",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://matchapro.web.bps.go.id/dirgc",
            "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "cookie": "" 
        }
        self.BASE_PAYLOAD = {
            "_token": "",
            "start": 0, "length": 1000, 
            "nama_usaha": "", "alamat_usaha": "",
            "provinsi": "", "kabupaten": "", "kecamatan": "", "desa": "",
            "status_filter": "semua", "rtotal": "0",
            "sumber_data": "", "skala_usaha": "", "idsbr": "", "history_profiling": ""
        }
    
    def log(self, msg):
        if self.logger:
            self.logger(msg)
        else:
            print(msg)

    def fetch_page(self, start, length, base_url):
        payload = self.BASE_PAYLOAD.copy()
        payload["start"] = str(start)
        payload["length"] = str(length)

        retry_delay = 5
        attempt = 0
        
        while True:
            attempt += 1
            try:
                r = self.session.post(base_url, data=payload, headers=self.HEADERS, timeout=30)
                if r.status_code != 200:
                    self.log(f"⚠️ [Offset {start}] Gagal (Status {r.status_code}). Retry {attempt} dalam {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 60)
                    continue
                
                data = r.json()
                if "data" in data and isinstance(data["data"], list):
                    # Success
                    if attempt > 1:
                        self.log(f"✅ [Offset {start}] Sukses setelah {attempt} percobaan.")
                    return data["data"] if len(data["data"]) > 0 else []
                else:
                     self.log(f"⚠️ [Offset {start}] Respons JSON tidak valid/kosong. Retry {attempt}...")
            
            except Exception as e:
                self.log(f"❌ [Offset {start}] Error: {e}. Retry {attempt} dalam {retry_delay}s...")
            
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 1.5, 60)


    def run_scraper(self, username, password, otp_code=None, workers=5, update_existing=True):
        self.log(f"Starting Scraper with User: {username}, Workers: {workers}")
        
        # Login
        page = None
        browser = None
        for i in range(3):
            try:
                page, browser = login_with_sso(username, password, otp_code, headless=True)
                if page: break
                time.sleep(3)
            except Exception as e:
                self.log(f"Login error: {e}")
                time.sleep(3)
        
        if not page:
             self.log("Login Gagal Fatal.")
             return

        try:
            url_gc = "https://matchapro.web.bps.go.id/direktori-usaha/data-gc-card"
            page.goto("https://matchapro.web.bps.go.id/dirgc")
            page.wait_for_load_state('networkidle')
            page.wait_for_selector('meta[name="csrf-token"]', state='attached', timeout=10000)

            # Tokens
            token_element = page.locator('meta[name="csrf-token"]')
            if token_element.count() > 0:
                self.BASE_PAYLOAD["_token"] = token_element.get_attribute('content')
            else:
                self.log("No _token")
                browser.close()
                return

            # Cookies
            cookies = page.context.cookies()
            self.HEADERS["cookie"] = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            
            # Wilayah
            try:
                r = self.session.get("https://matchapro.web.bps.go.id/direktori-usaha", headers=self.HEADERS, timeout=20)
                prov = re.search(r'<select id="f_provinsi".*?<option value="(\d+)" selected>', r.text, re.DOTALL)
                kab = re.search(r'<select id="f_kabupaten".*?<option value="(\d+)" selected>', r.text, re.DOTALL)
                self.BASE_PAYLOAD["provinsi"] = prov.group(1) if prov else ""
                self.BASE_PAYLOAD["kabupaten"] = kab.group(1) if kab else ""
                self.log(f"Wilayah: {self.BASE_PAYLOAD['provinsi']} - {self.BASE_PAYLOAD['kabupaten']}")
            except: pass

        except Exception as e:
            self.log(f"Setup error: {e}")
            if browser: browser.close()
            return
        
        if browser: browser.close()

        # Download Info
        try:
            p = self.BASE_PAYLOAD.copy()
            p["length"] = "1"
            r = self.session.post("https://matchapro.web.bps.go.id/direktori-usaha/data-gc-card", data=p, headers=self.HEADERS, timeout=20)
            total_records = r.json().get("recordsTotal", 0)
        except:
            self.log("Gagal get total records")
            return
            
        self.log(f"Total data: {total_records:,}")
        
        self.log(f"Total data: {total_records:,}")
        
        all_records = []
        final_list = [] # For filtered results
        length_per_req = 1000 
        offsets = list(range(0, total_records, length_per_req))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_offset = {
                executor.submit(self.fetch_page, start, length_per_req, "https://matchapro.web.bps.go.id/direktori-usaha/data-gc-card"): start 
                for start in offsets
            }
            completed = 0
            for future in concurrent.futures.as_completed(future_to_offset):
                offset = future_to_offset[future]
                try:
                    data = future.result()
                    if data:
                        all_records.extend(data)
                        completed += len(data)
                        if completed % 2000 == 0 or completed == total_records: 
                            self.log(f"Progress Download: {completed}/{total_records} data ({len(all_records)} saved buffer)")
                except Exception as e:
                    self.log(f"❌ Fatal Error fetching offset {offset}: {e}")

        # Clean & Save
        for record in all_records:
            for k in ['alamat_usaha', 'kegiatan_usaha', 'nama_usaha']:
                if k in record and isinstance(record[k], str):
                    record[k] = record[k].replace('\n', ' ').replace('\t', ' ').replace('\r', ' ')
            
            # --- Logic Update Isian & HasilGC ---
            # 1. Copy gcs_result -> hasilgc
            record['hasilgc'] = record.get('gcs_result', '')

            # 2. Filter logic
            # If update_existing is False AND gc_username is set (meaning already processed), SKIP it.
            if not update_existing and record.get('gc_username'):
                continue
            
            # 3. Add Edit Columns (Default to original values)
            record['nama_usaha_edit'] = record.get('nama_usaha', '')
            record['alamat_usaha_edit'] = record.get('alamat_usaha', '')
            
            final_list.append(record)

        all_records = final_list


        all_records = final_list


        # Use generic output name
        OUTPUT = "direktori_usaha_full_all_columns_2026.xlsx"
        try:
            import pandas as pd
            df = pd.DataFrame(all_records)
            # Ensure openpyxl is installed
            df.to_excel(OUTPUT, index=False)
            self.log(f"\n✅ Scraping Selesai! File saved: {OUTPUT}")
        except Exception as e:
            self.log(f"Failed to save CSV: {e}")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"MatchaPro Sender v{version} (Multi-Account)")
        self.geometry("700x750")
        
        self.running = False
        self.senders = [] # List of MatchaSender instances
        self.threads = []
        self.log_queue = queue.Queue()
        self.result_queue = queue.Queue() # Queue for worker updates
        self.accounts = [] # List of dicts {'username':, 'password':, 'otp':}
        self.vpn_config = {}
        
        self.load_accounts()
        self.load_vpn_config()
        self.load_settings()
        self._init_ui()
        self.check_playwright_browsers()
        self.process_log_queue()

    def _init_ui(self):
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Account Manager Section ---
        acc_frame = ttk.LabelFrame(main_frame, text="Account Manager", padding="10")
        acc_frame.pack(fill=tk.BOTH, expand=False, pady=5)
        
        # Input Fields
        input_frame = ttk.Frame(acc_frame)
        input_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(input_frame, text="Username:").grid(row=0, column=0, sticky="w")
        self.entry_user = ttk.Entry(input_frame, width=20)
        self.entry_user.grid(row=0, column=1, padx=5)
        
        ttk.Label(input_frame, text="Password:").grid(row=0, column=2, sticky="w")
        self.entry_pass = ttk.Entry(input_frame, width=20, show="*")
        self.entry_pass.grid(row=0, column=3, padx=5)
        
        ttk.Label(input_frame, text="OTP:").grid(row=0, column=4, sticky="w")
        self.entry_otp = ttk.Entry(input_frame, width=10)
        self.entry_otp.grid(row=0, column=5, padx=5)

        ttk.Label(input_frame, text="Workers:").grid(row=0, column=6, sticky="w")
        self.entry_workers = ttk.Entry(input_frame, width=5)
        self.entry_workers.insert(0, "1")
        self.entry_workers.grid(row=0, column=7, padx=5)
        
        btn_add = ttk.Button(input_frame, text="Add", command=self.add_account)
        btn_add.grid(row=0, column=8, padx=5)

        # List (Treeview)
        columns = ('username', 'password', 'otp', 'workers')
        self.tree = ttk.Treeview(acc_frame, columns=columns, show='headings', height=4)
        self.tree.heading('username', text='Username')
        self.tree.heading('password', text='Password')
        self.tree.heading('otp', text='OTP')
        self.tree.heading('workers', text='Workers')
        self.tree.column('username', width=150)
        self.tree.column('password', width=150) 
        self.tree.column('otp', width=80)
        self.tree.column('workers', width=60)
        self.tree.pack(fill=tk.X, pady=5)
        
        btn_remove = ttk.Button(acc_frame, text="Remove Selected", command=self.remove_account)
        btn_remove.pack(anchor='e')

        # --- Configuration Section ---
        config_frame = ttk.LabelFrame(main_frame, text="Configuration", padding="10")
        config_frame.pack(fill=tk.X, pady=5)
        
        # CSV/Excel
        csv_frame = ttk.Frame(config_frame)
        csv_frame.pack(fill=tk.X)
        ttk.Label(csv_frame, text="File Data:").pack(side=tk.LEFT)
        self.entry_csv = ttk.Entry(csv_frame)
        saved_csv = self.settings.get('last_csv', "data_gc_profiling_kirim.xlsx")
        self.entry_csv.insert(0, saved_csv)
        self.entry_csv.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(csv_frame, text="Browse", command=self.browse_csv).pack(side=tk.LEFT)
        
        # Settings
        settings_frame = ttk.Frame(config_frame)
        settings_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(settings_frame, text="Start Row:").pack(side=tk.LEFT)
        self.entry_row = ttk.Entry(settings_frame, width=8)
        self.entry_row.insert(0, self.get_last_row())
        self.entry_row.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(settings_frame, text="Delay (sec):").pack(side=tk.LEFT, padx=(10, 0))
        self.entry_delay = ttk.Entry(settings_frame, width=8)
        self.entry_delay.insert(0, "15")
        self.entry_delay.pack(side=tk.LEFT, padx=5)
        
        self.entry_delay.pack(side=tk.LEFT, padx=5)
        
        self.var_random = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="Randomize (+0-5s)", variable=self.var_random).pack(side=tk.LEFT, padx=10)
        
        self.var_headless = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="Headless", variable=self.var_headless).pack(side=tk.LEFT, padx=10)

        # New Checkbox for Update Isian
        self.var_update_db = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="Update Isian?", variable=self.var_update_db).pack(side=tk.LEFT, padx=10)

        # Timeout Settings
        timeout_frame = ttk.Frame(config_frame)
        timeout_frame.pack(fill=tk.X, pady=2)
        ttk.Label(timeout_frame, text="Req Timeout (s):").pack(side=tk.LEFT)
        self.entry_min_timeout = ttk.Entry(timeout_frame, width=5)
        self.entry_min_timeout.insert(0, "20")
        self.entry_min_timeout.pack(side=tk.LEFT, padx=2)
        ttk.Label(timeout_frame, text="-").pack(side=tk.LEFT)
        self.entry_max_timeout = ttk.Entry(timeout_frame, width=5)
        self.entry_max_timeout.insert(0, "40")
        self.entry_max_timeout.pack(side=tk.LEFT, padx=2)

        theme_frame = ttk.Frame(config_frame)
        theme_frame.pack(fill=tk.X, pady=5)
        ttk.Button(theme_frame, text="Tutorial", command=self.show_tutorial).pack(side=tk.RIGHT, padx=5)
        ttk.Button(theme_frame, text="Disclaimer", command=self.show_disclaimer).pack(side=tk.RIGHT, padx=5)




        # --- Actions ---
        
        # Warning Label
        lbl_warn = ttk.Label(main_frame, text="⚠️ PERINGATAN: Tutup File Excel saat aplikasi berjalan agar Auto-Save berhasil!", foreground="red", font=("Arial", 9, "bold"))
        lbl_warn.pack(pady=(5, 0))

        action_frame = ttk.Frame(main_frame, padding="5")
        action_frame.pack(fill=tk.X)
        self.btn_start = ttk.Button(action_frame, text="START ALL WORKERS", command=self.start_process)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.btn_stop = ttk.Button(action_frame, text="STOP", command=self.stop_process, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.btn_scraping = ttk.Button(action_frame, text="OPEN SCRAPING", command=self.launch_scraping)
        self.btn_scraping.pack(side=tk.RIGHT, padx=5)

        # --- Video Player (OpenCV + PIL) ---
        try:
            import cv2
            from PIL import Image, ImageTk
            
            video_frame = ttk.Frame(main_frame, padding="5")
            video_frame.pack(fill=tk.BOTH, expand=True, pady=5)
            
            self.lbl_video = ttk.Label(video_frame)
            self.lbl_video.pack(expand=True, fill="both")
            
            video_filename = "Video_Batu_Kertas_Gunting_Kalah_Tampar.mp4"
            
            if hasattr(sys, '_MEIPASS'):
                video_path = os.path.join(sys._MEIPASS, video_filename)
                if not os.path.exists(video_path):
                     video_path = os.path.join(sys._MEIPASS, "data", video_filename)
            else:
                 video_path = video_filename
                 if not os.path.exists(video_path):
                     video_path = os.path.join("data", video_filename)
            
            if os.path.exists(video_path):
                self.cap = cv2.VideoCapture(video_path)
                
                def stream_video():
                    if not self.running: # Check if app is closing
                        if getattr(self, 'cap', None):
                             try:
                                 ret, frame = self.cap.read()
                                 if ret:
                                     # Resize to fit (maintain aspect ratio roughly or fixed)
                                     # Let's fix height to 150px to not take too much space
                                     h = 150
                                     aspect = frame.shape[1] / frame.shape[0]
                                     w = int(h * aspect)
                                     frame = cv2.resize(frame, (w, h))
                                     
                                     # Convert color
                                     cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                     img = Image.fromarray(cv2image)
                                     imgtk = ImageTk.PhotoImage(image=img)
                                     
                                     self.lbl_video.imgtk = imgtk
                                     self.lbl_video.configure(image=imgtk)
                                     self.lbl_video.after(33, stream_video) # ~30 FPS
                                 else:
                                     # Loop
                                     self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                                     stream_video()
                             except:
                                 pass
                    else:
                        # Clean up if app closed (though this logic is loose)
                         pass

                # Start streaming
                # We need a flag to stop it when app closes or reuse self.running? 
                # self.running is for Sender. Let's make a generic alive flag if needed.
                # actually just rely on daemon or window exists.
                stream_video()
                
            else:
                ttk.Label(video_frame, text=f"Video tidak ditemukan di: {video_path}").pack()
                
        except Exception as e:
            print(f"Video Error: {e}")
            ttk.Label(main_frame, text=f"Video Player Error (CV2): {e}").pack()

        # --- Log ---
        log_frame = ttk.LabelFrame(main_frame, text="Logs", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_area = scrolledtext.ScrolledText(log_frame, state='disabled', height=10)
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def add_account(self):
        u = self.entry_user.get().strip()
        p = self.entry_pass.get().strip()
        o = self.entry_otp.get().strip()
        w = self.entry_workers.get().strip()
        
        try:
            w_count = int(w)
            if w_count < 1: w_count = 1
        except:
            w_count = 1

        if u and p:
            self.accounts.append({'username': u, 'password': p, 'otp': o, 'workers': w_count})
            self.refresh_tree()
            self.save_accounts()
            self.entry_user.delete(0, tk.END)
            self.entry_pass.delete(0, tk.END)
            self.entry_otp.delete(0, tk.END)
            # self.entry_workers.delete(0, tk.END) # keep 1
        else:
            messagebox.showwarning("Error", "Username and Password required")

    def remove_account(self):
        sel = self.tree.selection()
        if sel:
            for item in sel:
                idx = self.tree.index(item)
                del self.accounts[idx]
            self.refresh_tree()
            self.save_accounts()

    def refresh_tree(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for acc in self.accounts:
            # Mask password in UI
            masked_pass = "*" * len(acc['password'])
            workers = acc.get('workers', 1)
            self.tree.insert('', tk.END, values=(acc['username'], masked_pass, acc['otp'], workers))

    def load_accounts(self):
        try:
            if os.path.exists('accounts.json'):
                with open('accounts.json', 'r') as f:
                    self.accounts = json.load(f)
                self.refresh_tree()
        except Exception as e:
            self.log(f"Failed to load accounts: {e}")

    def load_vpn_config(self):
        try:
            if os.path.exists('vpn_config.json'):
                with open('vpn_config.json', 'r') as f:
                    self.vpn_config = json.load(f)
        except Exception:
            pass

    def load_settings(self):
        self.settings = {}
        try:
            if os.path.exists('settings.json'):
                with open('settings.json', 'r') as f:
                    self.settings = json.load(f)
        except Exception:
            pass

    def save_settings(self):
        try:
            with open('settings.json', 'w') as f:
                json.dump(self.settings, f)
        except Exception:
            pass

    def save_accounts(self):
        try:
            with open('accounts.json', 'w') as f:
                json.dump(self.accounts, f)
        except Exception:
            pass

    def log(self, message):
        self.log_queue.put(message)

    def process_log_queue(self):
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                self.log_area.config(state='normal')
                self.log_area.insert(tk.END, msg + "\n")
                self.log_area.see(tk.END)
                self.log_area.config(state='disabled')
            except:
                break
        self.after(100, self.process_log_queue)

    def browse_csv(self):
        f = filedialog.askopenfilename(filetypes=[("Excel/CSV", "*.xlsx *.xls *.csv")])
        if f:
            self.entry_csv.delete(0, tk.END)
            self.entry_csv.insert(0, f)
            self.settings['last_csv'] = f
            self.save_settings()

    def get_last_row(self):
        try:
            with open('baris.txt', 'r') as f: return f.read().strip()
        except: return "0"

    def check_playwright_browsers(self):
        # ... existing threading check ...
        def run_check():
            try:
                from playwright.__main__ import main as pw_cli
                old_argv = sys.argv
                sys.argv = [old_argv[0], "install", "chromium"]
                pw_cli()
            except SystemExit: pass
            except Exception as e: self.log(f"Browser check failed: {e}")
            finally: sys.argv = old_argv
            self.log("Browser components ready.")
        threading.Thread(target=run_check, daemon=True).start()

    def start_process(self):
        if not self.accounts:
            messagebox.showwarning("No Accounts", "Please add at least one account.")
            return
            
        csv_path = self.entry_csv.get().strip()
        if not os.path.exists(csv_path):
             messagebox.showerror("Error", "CSV File not found")
             return

        try:
            row_start = int(self.entry_row.get().strip())
            base_delay = float(self.entry_delay.get().strip())
            min_to = int(self.entry_min_timeout.get().strip())
            max_to = int(self.entry_max_timeout.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Check numeric inputs (Row, Delay, Timeout)")
            return

        self.running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.senders = []
        self.threads = []
        
        
        # Build flat list of workers
        worker_tasks = []
        for acc in self.accounts:
            count = acc.get('workers', 1)
            for _ in range(count):
                worker_tasks.append(acc)
                
        total_workers = len(worker_tasks)
        
        config = {
            'csv_path': csv_path,
            'row_start': row_start,
            'base_delay': base_delay,
            'use_random': self.var_random.get(),
            'timeout_min': min_to,
            'timeout_max': max_to,
            'headless': self.var_headless.get()
        }

        self.log(f"Starting {total_workers} workers from {len(self.accounts)} accounts...")
        
        # Define VPN Callback
        def vpn_callback_func():
            if self.var_vpn_auto.get():
                self.reconnect_vpn()
            else:
                self.log("VPN Callback triggered but Auto-Reconnect is disabled.")

        # Start Result Monitor
        self.result_queue = queue.Queue() 
        threading.Thread(target=self.monitor_results, args=(csv_path,), daemon=True).start()

        for i, acc in enumerate(worker_tasks):
            # Only the very first worker (ID 0) handles VPN callbacks
            is_primary = (i == 0)
            
            sender = MatchaSender(
                username=acc['username'],
                password=acc['password'],
                otp_code=acc['otp'],
                config=config,
                logger_callback=self.log,
                vpn_callback=vpn_callback_func if is_primary else None,
                result_queue=self.result_queue
            )
            self.senders.append(sender)
            t = threading.Thread(target=sender.run_worker, args=(i, total_workers))
            t.daemon = True
            t.start()
            self.threads.append(t)

        # Monitor thread
        threading.Thread(target=self.monitor_process, daemon=True).start()

    def vpn_settings_ui(self):
        vpn_win = tk.Toplevel(self)
        vpn_win.title("VPN Settings")
        vpn_win.geometry("400x350")
        
        ttk.Label(vpn_win, text="FortiClient Path:").pack(anchor='w', padx=10, pady=5)
        self.entry_vpn_path = ttk.Entry(vpn_win)
        self.entry_vpn_path.insert(0, self.vpn_config.get('path', r"C:\Program Files\Fortinet\FortiClient\FortiClient.exe"))
        self.entry_vpn_path.pack(fill=tk.X, padx=10)
        
        ttk.Label(vpn_win, text="VPN Server (ip:port):").pack(anchor='w', padx=10, pady=5)
        self.entry_vpn_server = ttk.Entry(vpn_win)
        self.entry_vpn_server.insert(0, self.vpn_config.get('server', ''))
        self.entry_vpn_server.pack(fill=tk.X, padx=10)
        
        ttk.Label(vpn_win, text="VPN Username:").pack(anchor='w', padx=10, pady=5)
        self.entry_vpn_user = ttk.Entry(vpn_win)
        self.entry_vpn_user.insert(0, self.vpn_config.get('username', ''))
        self.entry_vpn_user.pack(fill=tk.X, padx=10)
        
        ttk.Label(vpn_win, text="VPN Password:").pack(anchor='w', padx=10, pady=5)
        self.entry_vpn_pass = ttk.Entry(vpn_win, show="*")
        self.entry_vpn_pass.insert(0, self.vpn_config.get('password', ''))
        self.entry_vpn_pass.pack(fill=tk.X, padx=10)
        
        self.var_vpn_auto = tk.BooleanVar(value=self.vpn_config.get('auto', False))
        ttk.Checkbutton(vpn_win, text="Enable Auto Reconnect on Error", variable=self.var_vpn_auto).pack(anchor='w', padx=10, pady=10)
        
        def save():
            self.vpn_config = {
                'path': self.entry_vpn_path.get(),
                'server': self.entry_vpn_server.get(),
                'username': self.entry_vpn_user.get(),
                'password': self.entry_vpn_pass.get(),
                'auto': self.var_vpn_auto.get()
            }
            with open('vpn_config.json', 'w') as f:
                json.dump(self.vpn_config, f)
            vpn_win.destroy()
            self.log("VPN Config Saved.")
            
        ttk.Button(vpn_win, text="Save & Close", command=save).pack(pady=10)

    def reconnect_vpn(self):
        # Prevent multiple threads from triggering reconnection at once
        if hasattr(self, '_vpn_reconnecting') and self._vpn_reconnecting:
            self.log("VPN Reconnection already in progress...")
            return

        self._vpn_reconnecting = True
        self.log("\n⚠️ NETWORK ERROR DETECTED! INITIATING VPN RECONNECT...")
        
        path = self.vpn_config.get('path', '')
        server = self.vpn_config.get('server', '')
        user = self.vpn_config.get('username', '')
        pwd = self.vpn_config.get('password', '')
        
        if not os.path.exists(path):
            self.log(f"❌ VPN Exe not found: {path}")
            self._vpn_reconnecting = False
            return

        def run_vpn():
            try:
                # Kill existing (optional, might require admin)
                # os.system("taskkill /f /im FortiClient.exe") 
                
                # Attempt Connect
                # Standard CLI args for FortiSSLVPNclient: connect -h server:port -u user -p password
                # But user pointed to FortiClient.exe which often is GUI.
                # Use subprocess to try anyway.
                # Assuming FortiSSLVPNclient.exe syntax if it happens to be that one, 
                # or FortiClientConsole arguments.
                
                # Common syntax: FortiSSLVPNclient.exe connect -h <host>[:<port>] -u <user>[:<password>]
                cmd = [path, "connect", "-h", server, "-u", user + ":" + pwd]
                
                # Hide window
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                self.log(f"Executing: {path} connect -h {server} ...")
                subprocess.Popen(cmd, startupinfo=startupinfo)
                
                # Wait for interaction/connection
                import time
                for i in range(15):
                    self.log(f"Waiting for VPN... ({i+1}/15)")
                    time.sleep(1)
                    
                self.log("VPN Reconnect Sequence Finished (Check Status).")
                
            except Exception as e:
                self.log(f"VPN Reconnect Failed: {e}")
            finally:
                self._vpn_reconnecting = False
        
        threading.Thread(target=run_vpn, daemon=True).start()

    def monitor_results(self, csv_path):
        """
        Monitor result_queue and update the main Excel file asynchronously.
        """
        import pandas as pd
        import time
        
        # Load local DF for updates
        try:
            if csv_path.lower().endswith(('.xlsx', '.xls')):
                df = pd.read_excel(csv_path)
            else:
                # Basic CSV fallback
                try:
                    df = pd.read_csv(csv_path, sep=';', encoding='latin1')
                except:
                    df = pd.read_csv(csv_path)
        except Exception as e:
            self.log(f"Updater Thread Failed to Load: {e}")
            return

        updates_buffer = {}
        last_save = time.time()
        
        while self.running:
            try:
                # Non-blocking get
                data = self.result_queue.get(timeout=1)
                idx = data['index']
                user = data['username']
                
                # Update in memory
                if idx in df.index:
                    df.at[idx, 'gc_username'] = user
                    updates_buffer[idx] = user
            except queue.Empty:
                pass
            
            # Save every 30 seconds or if buffer is large
            if self.running and (time.time() - last_save > 30 or len(updates_buffer) > 10):
                if updates_buffer:
                    try:
                        # Save to same file (overwrite)
                        if csv_path.lower().endswith(('.xlsx', '.xls')):
                             df.to_excel(csv_path, index=False)
                        else:
                             df.to_csv(csv_path, index=False, sep=';')
                        
                        self.log(f"💾 Data Saved ({len(updates_buffer)} new updates)")
                        updates_buffer.clear()
                        last_save = time.time()
                    except Exception as e:
                        self.log(f"⚠️ Save Failed (File Open?): {e}")

    def stop_process(self):
        self.running = False
        self.log("Stopping all workers...")
        for s in self.senders:
            s.stop()
        self.btn_stop.config(state=tk.DISABLED)

    def monitor_process(self):
        # Wait for threads to finish? Or just generic monitoring
        # Since threads are daemon, we just wait/check alive?
        # Let's just periodically check if *any* are alive.
        import time
        while self.running:
            alive = any(t.is_alive() for t in self.threads)
            if not alive and self.threads:
                self.log("All threads finished.")
                self.running = False
                break
            time.sleep(1)
        
        self.after(0, self.reset_buttons)

    def reset_buttons(self):
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.senders = []
        self.threads = []





    def launch_scraping(self):
        # Gunakan thread terpisah agar UI tidak freeze
        t = threading.Thread(target=self._run_scraping_internal)
        t.daemon = True
        t.start()

    def _run_scraping_internal(self):
        self.btn_scraping.config(state=tk.DISABLED)
        self.log("🚀 Memulai proses scraping internal...")
        
        try:
            u, p, o = None, None, None
            if self.accounts:
                acc = self.accounts[0]
                u = acc['username']
                p = acc['password']
                o = acc['otp']
            
            if not u or not p:
                self.log("❌ Scraping Gagal: Tidak ada akun tersimpan. Tambahkan akun dulu.")
                self.btn_scraping.config(state=tk.NORMAL)
                return

            scraper = MatchaScraper(logger=self.log)
            scraper.run_scraper(
                username=u, 
                password=p, 
                otp_code=o, 
                workers=3, 
                update_existing=self.var_update_db.get()
            )
            
        except Exception as e:
            self.log(f"❌ Scraping Error: {e}")
        finally:
             self.btn_scraping.config(state=tk.NORMAL)

    def show_tutorial(self):
        t = tk.Toplevel(self)
        t.title("Tutorial & Cara Penggunaan")
        t.geometry("600x500")

        txt = scrolledtext.ScrolledText(t, wrap=tk.WORD, width=70, height=25)
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tutorial_text = """
=== CARA PENGGUNAAN APLIKASI ===

A. PENJELASAN SETTINGS (CHECKBOX)
1. Enable Auto Reconnect: Jika VPN putus, aplikasi mencoba menghubungkan ulang otomatis (perlu setup config VPN).
2. Randomize (+0-5s): Menambah jeda acak 0-5 detik setiap kirim data agar aktivitas terlihat lebih natural.
3. Headless: Browser berjalan di background (tidak muncul window). Lebih ringan & cepat.
4. Update Isian?: 
   - ON (Dicentang): Scraping akan mengambil dan menyimpan SEMUA data, serta mengupdate nilai 'hasilgc'.
   - OFF (Tidak): Scraping akan MELEWATI (SKIP) data yang sudah memiliki 'gc_username' (sudah pernah diproses).

B. LANGKAH-LANGKAH PENGGUNAAN
1. SCRAPING DATA (MENDAPATKAN DATA BARU)
   - Pastikan akun sudah ditambahkan di "Account Manager".
   - Atur checkbox "Update Isian?" sesuai kebutuhan (lihat penjelasan di atas).
   - Klik tombol "OPEN SCRAPING".
   - Aplikasi akan otomatis menggunakan akun pertama untuk login.
   - Hasil scraping otomatis tersimpan sebagai file Excel (misal: direktori_usaha_full_all_columns_2026.xlsx).

2. PERSIAPAN FILE (PENTING!)
   - Buka file Excel hasil scraping tadi.
   - Kolom "hasilgc" biasanya sudah otomatis terisi dari hasil scraping (gcs_result).
   - Pastikan/Edit kolom "hasilgc" dengan kode:
        • 1  = Ditemukan / Ada
        • 3  = Tutup / Pindah
        • 4  = Ganda
        • 99 = Tidak Ditemukan
   - Untuk status 1 (Ditemukan), pastikan kolom "latitude" dan "longitude" terisi.
   - Simpan kembali filenya.

3. SETTING FILE DI APLIKASI
   - Klik "Browse" di bagian Configuration.
   - Pilih file Excel/CSV yang siap kirim.
   - Pastikan "Start Row" 0 (atau sesuai keinginan).

4. MENJALANKAN PENGIRIMAN
   - Masukkan akun-akun di Account Manager.
   - Workers = jumlah tab browser simultan per akun.
   - Klik "Add" untuk memasukkan ke list.
   - Klik "START ALL WORKERS" untuk memulai pengiriman.

5. MONITORING
   - Log aktivitas akan muncul di bagian bawah.
   - Jika ada error 429 (Rate Limit), script akan otomatis menunggu.
   - File "baris.txt" menyimpan progress terakhir agar bisa dilanjutkan nanti.
"""
        txt.insert(tk.END, tutorial_text)
        txt.config(state='disabled')

    def show_disclaimer(self):
        d = tk.Toplevel(self)
        d.title("DISCLAIMER PENTING")
        d.geometry("500x350")
        
        msg = ("Aplikasi ini hanya dibuat untuk membantu entri, TIDAK untuk melanggar aturan dari GC.\n\n"
               "Diskusikan dengan Ketua Tim dan Pimpinan.\n\n"
               "Motifnya bukan untuk banyak-banyakan, tapi memudahkan pekerjaan yang berulang, "
               "memudahkan menandai GC usaha yang sudah diprofiling pada kegiatan profiling sebelumnya "
               "dengan keyakinan bahwa ini sudah merupakan upaya terbaik.\n\n"
               "Pastikan data yang akan dikirim adalah data yang VALID dan sesuai ketentuan.\n\n"
               "DATA ADALAH TANGGUNG JAWAB SELURUH SATKER YANG MENGGUNAKAN APLIKASI INI, "
               "BUKAN TANGGUNG JAWAB DEVELOPER.\n\n"
               "by. AAK")
               
        lbl = ttk.Label(d, text=msg, wraplength=450, justify=tk.CENTER, font=("Arial", 10))
        lbl.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    
    # Init App with Video Path Fix
    app = App()
    
    # Inject Logic for Video Path Discovery inside App.__init__ or here?
    # Actually, we should update the video loading block in __init__
    # Because __init__ runs when App() is instantiated.
    # Let's verify if we need to modify App class init for video path.
    # Yes, we do.
    
    app.mainloop()
