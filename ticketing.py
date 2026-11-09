"""
Sistem Ticketing Online Wisata Curug Cipeteuy - TAHAP 1 (versi terminal)
Hanya memakai library bawaan Python 3 (tanpa instalasi tambahan).

Struktur:
  BAGIAN 1 - Konfigurasi (tarif, kuota)
  BAGIAN 2 - Database (SQLite)
  BAGIAN 3 - Logika bisnis (nanti dipakai ulang oleh Flask di tahap web)
  BAGIAN 4 - Tampilan menu terminal
"""
import os
import sqlite3
import random
import string
from datetime import date, datetime

from werkzeug.security import check_password_hash, generate_password_hash

# ============ BAGIAN 1 - KONFIGURASI (data contoh) ============
DB_FILE = os.environ.get("DB_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cipeteuy.db"))
KUOTA_HARIAN = 300
PIN_ADMIN = "020506"

TARIF = {                       # (hari biasa, akhir pekan)
    "dewasa": ("Dewasa", 15000, 20000),
    "anak":   ("Anak (3-12 th)", 10000, 12000),
}
TAMBAHAN = {
    "motor":   ("Parkir motor", 5000),
    "mobil":   ("Parkir mobil", 10000),
    "pemandu": ("Pemandu lokal", 50000),
}
METODE_BAYAR = ["QRIS", "Virtual Account", "GoPay", "DANA", "ShopeePay"]


# ============ BAGIAN 2 - DATABASE ============
def koneksi():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def buat_tabel():
    with koneksi() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS pengaturan (
            kunci TEXT PRIMARY KEY, nilai TEXT);
        CREATE TABLE IF NOT EXISTS tanggal_tutup (
            tanggal TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS pesanan (
            kode TEXT PRIMARY KEY,
            tanggal_kunjungan TEXT NOT NULL,
            nama TEXT NOT NULL,
            hp TEXT NOT NULL,
            dewasa INTEGER NOT NULL,
            anak INTEGER NOT NULL,
            tambahan TEXT,
            total INTEGER NOT NULL,
            metode TEXT,
            status TEXT NOT NULL,           -- Aktif / Terpakai / Dibatalkan
            dibuat_pada TEXT NOT NULL,
            dipakai_pada TEXT);
        CREATE TABLE IF NOT EXISTS pengguna (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL,
            hp TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            dibuat_pada TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS log_scan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kode TEXT, hasil TEXT, waktu TEXT);
        """)
        c.execute("INSERT OR IGNORE INTO pengaturan VALUES ('kuota', ?)",
                  (str(KUOTA_HARIAN),))


# ============ BAGIAN 3 - LOGIKA BISNIS ============
def akhir_pekan(tgl: str) -> bool:
    return date.fromisoformat(tgl).weekday() >= 5


def format_rp(n: int) -> str:
    return "Rp{:,}".format(n).replace(",", ".")


def ambil_kuota() -> int:
    with koneksi() as c:
        return int(c.execute("SELECT nilai FROM pengaturan WHERE kunci='kuota'").fetchone()[0])


def atur_kuota(jumlah: int):
    with koneksi() as c:
        c.execute("UPDATE pengaturan SET nilai=? WHERE kunci='kuota'", (str(jumlah),))


def tiket_terjual(tgl: str) -> int:
    with koneksi() as c:
        r = c.execute("""SELECT COALESCE(SUM(dewasa+anak),0) FROM pesanan
                         WHERE tanggal_kunjungan=? AND status!='Dibatalkan'""", (tgl,)).fetchone()
        return r[0]


def sisa_kuota(tgl: str) -> int:
    return max(0, ambil_kuota() - tiket_terjual(tgl))


def sedang_tutup(tgl: str) -> bool:
    with koneksi() as c:
        return c.execute("SELECT 1 FROM tanggal_tutup WHERE tanggal=?", (tgl,)).fetchone() is not None


def hitung_total(tgl: str, dewasa: int, anak: int, tambahan: dict) -> int:
    i = 2 if akhir_pekan(tgl) else 1
    total = dewasa * TARIF["dewasa"][i] + anak * TARIF["anak"][i]
    for kode, qty in tambahan.items():
        total += qty * TAMBAHAN[kode][1]
    return total


def validasi_pesanan(tgl, nama, hp, dewasa, anak):
    """Mengembalikan pesan error (str) atau None kalau semua valid."""
    try:
        t = date.fromisoformat(tgl)
    except ValueError:
        return "Format tanggal salah. Gunakan YYYY-MM-DD, contoh 2026-11-15."
    if t < date.today():
        return "Tanggal kunjungan tidak boleh sebelum hari ini."
    if sedang_tutup(tgl):
        return "Objek wisata ditutup pada tanggal tersebut."
    if len(nama.strip()) < 3:
        return "Nama minimal 3 karakter."
    if not (hp.isdigit() and hp.startswith("08") and 10 <= len(hp) <= 13):
        return "Nomor HP tidak valid. Contoh: 081234567890."
    if dewasa + anak < 1:
        return "Pilih minimal 1 tiket."
    if dewasa + anak > sisa_kuota(tgl):
        return f"Kuota tidak cukup. Sisa kuota tanggal itu: {sisa_kuota(tgl)}."
    return None


def buat_kode() -> str:
    huruf = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return "CPT-" + huruf


def simpan_pesanan(tgl, nama, hp, dewasa, anak, tambahan, metode) -> dict:
    """Simulasi: pembayaran dianggap langsung berhasil."""
    kode = buat_kode()
    total = hitung_total(tgl, dewasa, anak, tambahan)
    ket = ", ".join(f"{TAMBAHAN[k][0]} x{q}" for k, q in tambahan.items() if q > 0)
    with koneksi() as c:
        c.execute("""INSERT INTO pesanan VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                  (kode, tgl, nama.strip(), hp, dewasa, anak, ket, total, metode,
                   "Aktif", datetime.now().strftime("%Y-%m-%d %H:%M")))
    return {"kode": kode, "total": total}


def cari_pesanan(kode: str):
    with koneksi() as c:
        return c.execute("SELECT * FROM pesanan WHERE kode=?", (kode.strip().upper(),)).fetchone()


def pesanan_by_hp(hp: str):
    with koneksi() as c:
        return c.execute("SELECT * FROM pesanan WHERE hp=? ORDER BY dibuat_pada DESC", (hp,)).fetchall()


def batalkan(kode: str) -> str:
    p = cari_pesanan(kode)
    if not p:
        return "Kode tiket tidak ditemukan."
    if p["status"] != "Aktif":
        return f"Tiket tidak bisa dibatalkan (status: {p['status']})."
    with koneksi() as c:
        c.execute("UPDATE pesanan SET status='Dibatalkan' WHERE kode=?", (p["kode"],))
    return "OK"


def scan_tiket(kode: str):
    """Validasi tiket di gerbang. Mengembalikan (berhasil: bool, pesan: str)."""
    p = cari_pesanan(kode)
    if not p:
        hasil = (False, "TIDAK VALID: kode tidak ditemukan.")
    elif p["status"] == "Dibatalkan":
        hasil = (False, "DITOLAK: tiket sudah dibatalkan.")
    elif p["status"] == "Terpakai":
        hasil = (False, f"DITOLAK: tiket sudah dipakai pada {p['dipakai_pada']}.")
    elif p["tanggal_kunjungan"] != date.today().isoformat():
        hasil = (False, f"DITOLAK: tiket berlaku untuk {p['tanggal_kunjungan']}.")
    else:
        with koneksi() as c:
            c.execute("UPDATE pesanan SET status='Terpakai', dipakai_pada=? WHERE kode=?",
                      (datetime.now().strftime("%Y-%m-%d %H:%M"), p["kode"]))
        hasil = (True, f"VALID: silakan masuk. {p['dewasa']} dewasa, {p['anak']} anak ({p['nama']}).")
    with koneksi() as c:
        c.execute("INSERT INTO log_scan (kode, hasil, waktu) VALUES (?,?,?)",
                  (kode.strip().upper(), hasil[1], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return hasil


def tutup_tanggal(tgl: str):
    with koneksi() as c:
        c.execute("INSERT OR IGNORE INTO tanggal_tutup VALUES (?)", (tgl,))


def daftar_tutup():
    with koneksi() as c:
        return [r[0] for r in c.execute("SELECT tanggal FROM tanggal_tutup ORDER BY tanggal")]


def buka_tanggal(tgl: str):
    with koneksi() as c:
        c.execute("DELETE FROM tanggal_tutup WHERE tanggal=?", (tgl,))


def ringkasan() -> dict:
    with koneksi() as c:
        r = c.execute("""SELECT
            COALESCE(SUM(CASE WHEN status!='Dibatalkan' THEN total END),0) AS pendapatan,
            COALESCE(SUM(CASE WHEN status!='Dibatalkan' THEN dewasa+anak END),0) AS terjual,
            COALESCE(SUM(CASE WHEN status='Terpakai' THEN dewasa+anak END),0) AS masuk,
            COUNT(*) AS jumlah_pesanan FROM pesanan""").fetchone()
        return dict(r)


def semua_pesanan():
    with koneksi() as c:
        return c.execute("SELECT * FROM pesanan ORDER BY dibuat_pada DESC").fetchall()


# ---------- Akun pengunjung ----------
def hp_valid(hp: str) -> bool:
    return hp.isdigit() and hp.startswith("08") and 10 <= len(hp) <= 13


def daftar_pengguna(nama: str, hp: str, password: str, ulang: str):
    """Mengembalikan (pengguna dict, None) kalau berhasil, atau (None, pesan error)."""
    nama, hp = nama.strip(), hp.strip()
    if len(nama) < 3:
        return None, "Nama minimal 3 karakter."
    if not hp_valid(hp):
        return None, "Nomor HP tidak valid. Contoh: 081234567890."
    if len(password) < 6:
        return None, "Kata sandi minimal 6 karakter."
    if password != ulang:
        return None, "Konfirmasi kata sandi tidak sama."
    try:
        with koneksi() as c:
            cur = c.execute("INSERT INTO pengguna (nama, hp, password_hash, dibuat_pada) VALUES (?,?,?,?)",
                            (nama, hp, generate_password_hash(password),
                             datetime.now().strftime("%Y-%m-%d %H:%M")))
            return {"id": cur.lastrowid, "nama": nama, "hp": hp}, None
    except sqlite3.IntegrityError:
        return None, "Nomor HP ini sudah terdaftar. Silakan masuk."


def login_pengguna(hp: str, password: str):
    """Mengembalikan dict pengguna kalau cocok, kalau tidak None."""
    with koneksi() as c:
        u = c.execute("SELECT * FROM pengguna WHERE hp=?", (hp.strip(),)).fetchone()
    if u and check_password_hash(u["password_hash"], password):
        return {"id": u["id"], "nama": u["nama"], "hp": u["hp"]}
    return None


# ============ BAGIAN 4 - TAMPILAN MENU TERMINAL ============
def garis():
    print("-" * 60)


def input_angka(prompt: str, minimal=0) -> int:
    while True:
        s = input(prompt).strip()
        if s.isdigit() and int(s) >= minimal:
            return int(s)
        print("  Masukkan angka yang benar.")


def tampil_pesanan(p):
    print(f"  Kode      : {p['kode']}")
    print(f"  Tanggal   : {p['tanggal_kunjungan']}")
    print(f"  Pemesan   : {p['nama']} ({p['hp']})")
    print(f"  Tiket     : {p['dewasa']} dewasa, {p['anak']} anak")
    if p["tambahan"]:
        print(f"  Tambahan  : {p['tambahan']}")
    print(f"  Total     : {format_rp(p['total'])} ({p['metode']})")
    print(f"  Status    : {p['status']}")


def menu_info():
    garis()
    print("CURUG CIPETEUY - Informasi")
    print("Jam buka : 07.00 - 17.00 WIB setiap hari")
    print("Lokasi   : Kab. Majalengka, Jawa Barat")
    print("Tarif (hari biasa / akhir pekan):")
    for _, (nama, w, e) in TARIF.items():
        print(f"  {nama:<16} {format_rp(w)} / {format_rp(e)}")
    print("Tambahan:")
    for _, (nama, h) in TAMBAHAN.items():
        print(f"  {nama:<16} {format_rp(h)}")
    garis()


def menu_pesan():
    garis()
    print("PESAN TIKET")
    tgl = input("Tanggal kunjungan (YYYY-MM-DD): ").strip()
    if sedang_tutup(tgl):
        print("Maaf, objek wisata ditutup pada tanggal itu.")
        return
    try:
        print(f"Sisa kuota {tgl}: {sisa_kuota(tgl)}"
              f" ({'akhir pekan' if akhir_pekan(tgl) else 'hari biasa'})")
    except ValueError:
        print("Format tanggal salah. Contoh: 2026-11-15")
        return
    dewasa = input_angka("Jumlah tiket dewasa : ")
    anak = input_angka("Jumlah tiket anak   : ")
    tambahan = {}
    for kode, (nama, harga) in TAMBAHAN.items():
        tambahan[kode] = input_angka(f"{nama} ({format_rp(harga)}) jumlah: ")
    nama = input("Nama lengkap     : ")
    hp = input("Nomor HP (08xxx) : ").strip()

    err = validasi_pesanan(tgl, nama, hp, dewasa, anak)
    if err:
        print("Gagal:", err)
        return

    total = hitung_total(tgl, dewasa, anak, tambahan)
    print(f"\nTotal bayar: {format_rp(total)}")
    print("Metode pembayaran:")
    for i, m in enumerate(METODE_BAYAR, 1):
        print(f"  {i}. {m}")
    pilih = input_angka("Pilih metode (nomor): ", 1)
    if pilih > len(METODE_BAYAR):
        print("Pilihan tidak ada. Pesanan dibatalkan.")
        return
    if input("Konfirmasi bayar (simulasi)? (y/n): ").lower() != "y":
        print("Pesanan dibatalkan.")
        return

    hasil = simpan_pesanan(tgl, nama, hp, dewasa, anak, tambahan, METODE_BAYAR[pilih - 1])
    print("\nPEMBAYARAN BERHASIL")
    print(f"Kode e-tiket kamu: {hasil['kode']}")
    print("Tunjukkan kode ini (nanti berupa QR) ke petugas gerbang.")


def menu_tiket_saya():
    garis()
    hp = input("Masukkan nomor HP saat memesan: ").strip()
    data = pesanan_by_hp(hp)
    if not data:
        print("Belum ada tiket untuk nomor ini.")
        return
    for p in data:
        tampil_pesanan(p)
        print()
    kode = input("Kode tiket yang mau dibatalkan (Enter untuk lewati): ").strip()
    if kode:
        hasil = batalkan(kode)
        print("Tiket dibatalkan." if hasil == "OK" else hasil)


def menu_scanner():
    garis()
    print("SCANNER PETUGAS GERBANG (ketik 'x' untuk keluar)")
    while True:
        kode = input("Kode tiket: ").strip()
        if kode.lower() == "x":
            break
        ok, pesan = scan_tiket(kode)
        print(("  [OK] " if ok else "  [X]  ") + pesan)


def menu_admin():
    if input("PIN admin: ").strip() != PIN_ADMIN:
        print("PIN salah.")
        return
    while True:
        garis()
        r = ringkasan()
        print("DASHBOARD ADMIN")
        print(f"Pendapatan: {format_rp(r['pendapatan'])} | Tiket terjual: {r['terjual']} "
              f"| Sudah masuk: {r['masuk']} | Pesanan: {r['jumlah_pesanan']}")
        print(f"Kuota harian: {ambil_kuota()} | Terjual hari ini: {tiket_terjual(date.today().isoformat())}")
        print("1. Lihat semua pesanan")
        print("2. Ubah kuota harian")
        print("3. Tutup tanggal")
        print("4. Buka kembali tanggal")
        print("5. Ekspor laporan CSV")
        print("0. Kembali")
        p = input("Pilih: ").strip()
        if p == "1":
            data = semua_pesanan()
            if not data:
                print("Belum ada pesanan.")
            for d in data:
                print(f"{d['kode']} | {d['tanggal_kunjungan']} | {d['nama']:<15} | "
                      f"{d['dewasa']+d['anak']:>2} org | {format_rp(d['total']):>10} | {d['status']}")
        elif p == "2":
            atur_kuota(input_angka("Kuota baru: ", 10))
            print("Kuota diperbarui.")
        elif p == "3":
            tutup_tanggal(input("Tanggal ditutup (YYYY-MM-DD): ").strip())
            print("Tanggal ditutup.")
        elif p == "4":
            buka_tanggal(input("Tanggal dibuka (YYYY-MM-DD): ").strip())
            print("Tanggal dibuka.")
        elif p == "5":
            ekspor_csv()
        elif p == "0":
            break


def ekspor_csv():
    import csv
    nama_file = "laporan_pesanan.csv"
    with open(nama_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kode", "tanggal", "nama", "hp", "dewasa", "anak", "total", "metode", "status"])
        for d in semua_pesanan():
            w.writerow([d["kode"], d["tanggal_kunjungan"], d["nama"], d["hp"],
                        d["dewasa"], d["anak"], d["total"], d["metode"], d["status"]])
    print(f"Laporan disimpan ke {nama_file}")


def main():
    buat_tabel()
    while True:
        garis()
        print("TIKET ONLINE CURUG CIPETEUY")
        print("1. Informasi wisata")
        print("2. Pesan tiket")
        print("3. Tiket saya")
        print("4. Scanner petugas")
        print("5. Admin")
        print("0. Keluar")
        p = input("Pilih menu: ").strip()
        if p == "1":
            menu_info()
        elif p == "2":
            menu_pesan()
        elif p == "3":
            menu_tiket_saya()
        elif p == "4":
            menu_scanner()
        elif p == "5":
            menu_admin()
        elif p == "0":
            print("Terima kasih.")
            break
        else:
            print("Menu tidak ada.")


if __name__ == "__main__":
    main()
