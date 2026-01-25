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

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"MatchaPro Sender v{version} (Multi-Account)")
        self.geometry("700x750")
        
        self.running = False
        self.senders = [] # List of MatchaSender instances
        self.threads = []
        self.log_queue = queue.Queue()
        self.accounts = [] # List of dicts {'username':, 'password':, 'otp':}
        self.vpn_config = {}
        
        self.load_accounts()
        self.load_vpn_config()
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
        
        # CSV
        csv_frame = ttk.Frame(config_frame)
        csv_frame.pack(fill=tk.X)
        ttk.Label(csv_frame, text="File CSV:").pack(side=tk.LEFT)
        self.entry_csv = ttk.Entry(csv_frame)
        self.entry_csv.insert(0, "data_gc_profiling_kirim.csv")
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
        
        self.var_headless = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Headless", variable=self.var_headless).pack(side=tk.LEFT, padx=10)

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
        ttk.Button(theme_frame, text="VPN Settings", command=self.vpn_settings_ui).pack(side=tk.RIGHT, padx=5)

        # --- Actions ---
        action_frame = ttk.Frame(main_frame, padding="5")
        action_frame.pack(fill=tk.X)
        self.btn_start = ttk.Button(action_frame, text="START ALL WORKERS", command=self.start_process)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.btn_stop = ttk.Button(action_frame, text="STOP", command=self.stop_process, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

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
        f = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if f:
            self.entry_csv.delete(0, tk.END)
            self.entry_csv.insert(0, f)

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

        for i, acc in enumerate(worker_tasks):
            # Only the very first worker (ID 0) handles VPN callbacks
            is_primary = (i == 0)
            
            sender = MatchaSender(
                username=acc['username'],
                password=acc['password'],
                otp_code=acc['otp'],
                config=config,
                logger_callback=self.log,
                vpn_callback=vpn_callback_func if is_primary else None
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

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    app = App()
    app.mainloop()
