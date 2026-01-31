# 🚀 MatchaPro Sender v1.3.4 - Panduan Penggunaan

Aplikasi otomatisasi untuk **MatchaPro Mobile**.

## ✨ Fitur Baru (v1.3.4)

1.  **Update Nama & Alamat Usaha**: 
    - Sekarang Anda bisa mengupdate `nama_usaha` dan `alamat_usaha` langsung dari Excel!
    - Cukup isi kolom `nama_usaha_edit` dan `alamat_usaha_edit`.
    - Jika kosong, aplikasi akan menggunakan nama/alamat asli.
2.  **Struktur Lebih Rapi**: Folder proyek tidak lagi berantakan. File-file lama dipindahkan ke `archive/`.
3.  **Build System**: Gunakan `build.bat` untuk membuat file `.exe` sendiri.

---

## 📋 Persiapan Awal

1.  **Install Python (3.11 - 3.13)** 🐍
    Pasang Python dan pastikan dicentang "Add Python to PATH" saat instalasi.

2.  **Install Modul & Browser** 📦
    Jalankan perintah ini di Command Prompt / Terminal (di dalam folder folder ini):
    ```bash
    pip install -r requirements.txt
    playwright install
    ```

3.  **Siapkan Data (Excel/CSV)** 📊
    Format file input yang didukung: `.xlsx`, `.xls`, `.csv`.
    
    **Kolom Wajib:**
    - `perusahaan_id` (ID harus persis)
    - `latitude` (Gunakan titik/koma)
    - `longitude` (Gunakan titik/koma)
    - `hasilgc` (Kode status GC)
    
    **Kolom Opsional (Untuk Update Nama/Alamat):**
    - `nama_usaha_edit` (Isi jika ingin mengubah nama usaha)
    - `alamat_usaha_edit` (Isi jika ingin mengubah alamat)

    **Kode `hasilgc`:**
    - `99`: Tidak Ditemukan
    - `1`: Ditemukan (Aktif)
    - `3`: Tutup
    - `4`: Ganda

---

## 🖥️ Cara Menjalankan

### Cara 1: Menggunakan Aplikasi (Recommended) 🏆

1.  Jalankan file **`build.bat`**.
2.  Tunggu proses selesai, akan muncul folder `dist`.
3.  Buka `dist/MatchaProSender_v1.3.4.exe`.
4.  Masukkan akun, pilih file Excel, atur delay, lalu klik **START**.

### Cara 2: Menggunakan Script Manual 🛠️

Jika ingin menjalankan via terminal:
```bash
python app.py
```
Atau script CLI (tanpa GUI):
```bash
python tandaiKirim.py <username> <password> <otp_optional>
```

---

## ⚠️ Disclaimer

> **Gunakan script ini dengan bijak.** Jangan sampai melanggar aturan dari GC. Diskusikan dengan Ketua Tim dan Pimpinan.
>
> **Motif Penggunaan:** Script ini bukan untuk "banyak-banyakan" data, tetapi untuk:
> 1. Memudahkan pekerjaan yang berulang.
> 2. Memudahkan penandaan GC usaha yang **sudah diprofiling** pada kegiatan profiling sebelumnya.
> 3. Memberikan keyakinan bahwa data yang dikirim adalah upaya terbaik (best effort).
>
> **PENTING:** Pastikan data yang akan dikirim adalah data yang **valid** dan sesuai ketentuan.

## 💡 Tips Tambahan
- **Baris.txt**: Script otomatis menyimpan baris terakhir yang diproses di file `baris.txt`. Jika ingin mulai dari awal, hapus file ini atau set ke 0.
- **Error**: Jika ada error koneksi atau timeout, cek log atau file `error.txt`.

**Happy GC! 🎉**
