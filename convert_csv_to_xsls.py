import pandas as pd

def csv_to_excel(csv_path, excel_path, encoding="utf-8"):
    try:
        # Baca CSV
        df = pd.read_csv(csv_path, encoding=encoding)

        # Simpan ke Excel
        df.to_excel(excel_path, index=False, engine="openpyxl")

        print(f"Berhasil mengonversi: {csv_path} → {excel_path}")
        print(f"Jumlah baris: {len(df)}, kolom: {len(df.columns)}")

    except Exception as e:
        print("Gagal konversi CSV ke Excel")
        raise e


if __name__ == "__main__":
    csv_to_excel("direktori_usaha_checked_updated.csv", "direktori_usaha_checked_updated.xlsx")
