"""Tahap 2 - Versi web (Flask) sistem ticketing Curug Cipeteuy.
Logika bisnis dipakai ulang dari ticketing.py (tahap 1)."""
import csv
import io
import os
from datetime import date
from functools import wraps

from flask import (Flask, Response, abort, flash, jsonify, redirect,
                   render_template, request, session, url_for)

import ticketing as t

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ganti-kunci-ini-saat-publikasi")
t.buat_tabel()


@app.context_processor
def inject():
    return {"rp": t.format_rp, "hari_ini": date.today().isoformat(),
            "user": session.get("user")}


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*a, **kw)
    return wrapper


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("user"):
            return redirect(url_for("login", next=request.path))
        return f(*a, **kw)
    return wrapper


def next_aman(default):
    """Hanya terima alamat internal agar tidak jadi open redirect."""
    nxt = request.args.get("next", "")
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else default


def angka(v, maks=50):
    try:
        return max(0, min(maks, int(v)))
    except (TypeError, ValueError):
        return 0


# ---------- Halaman pengunjung ----------
@app.route("/")
def index():
    return render_template("index.html", tarif=t.TARIF, tambahan=t.TAMBAHAN)


@app.route("/pesan", methods=["GET", "POST"])
def pesan():
    form = request.form
    if request.method == "GET" and session.get("user"):   # isi otomatis untuk yang sudah login
        form = {"nama": session["user"]["nama"], "hp": session["user"]["hp"]}
    ctx = dict(tarif=t.TARIF, tambahan=t.TAMBAHAN, metode=t.METODE_BAYAR, form=form)
    if request.method == "POST":
        tgl = request.form.get("tanggal", "").strip()
        nama = request.form.get("nama", "")
        hp = request.form.get("hp", "").strip()
        dewasa, anak = angka(request.form.get("dewasa")), angka(request.form.get("anak"))
        tambahan = {k: angka(request.form.get(k), 10) for k in t.TAMBAHAN}
        metode = request.form.get("metode")
        if metode not in t.METODE_BAYAR:
            flash("Pilih metode pembayaran.", "error")
            return render_template("pesan.html", **ctx)
        err = t.validasi_pesanan(tgl, nama, hp, dewasa, anak)
        if err:
            flash(err, "error")
            return render_template("pesan.html", **ctx)
        hasil = t.simpan_pesanan(tgl, nama, hp, dewasa, anak, tambahan, metode)
        return redirect(url_for("tiket", kode=hasil["kode"]))
    return render_template("pesan.html", **ctx)


@app.route("/api/kuota")
def api_kuota():
    tgl = request.args.get("tanggal", "")
    try:
        date.fromisoformat(tgl)
    except ValueError:
        return jsonify(ok=False)
    return jsonify(ok=True, tutup=t.sedang_tutup(tgl), sisa=t.sisa_kuota(tgl),
                   akhir_pekan=t.akhir_pekan(tgl))


@app.route("/tiket/<kode>")
def tiket(kode):
    p = t.cari_pesanan(kode)
    if not p:
        abort(404)
    return render_template("tiket.html", p=p)


@app.route("/cari", methods=["GET", "POST"])
def cari():
    data, hp = None, ""
    if request.method == "POST":
        hp = request.form.get("hp", "").strip()
        data = t.pesanan_by_hp(hp)
    return render_template("cari.html", data=data, hp=hp)


@app.route("/batal", methods=["POST"])
def batal():
    kode, hp = request.form.get("kode", ""), request.form.get("hp", "")
    p = t.cari_pesanan(kode)
    if not p or p["hp"] != hp:
        flash("Tiket tidak ditemukan.", "error")
    else:
        hasil = t.batalkan(kode)
        flash("Tiket berhasil dibatalkan." if hasil == "OK" else hasil,
              "ok" if hasil == "OK" else "error")
    return redirect(url_for("cari"))


# ---------- Akun pengunjung ----------
@app.route("/masuk", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("akun"))
    hp = ""
    if request.method == "POST":
        hp = request.form.get("hp", "").strip()
        u = t.login_pengguna(hp, request.form.get("password", ""))
        if u:
            session["user"] = u
            flash("Selamat datang, %s." % u["nama"], "ok")
            return redirect(next_aman(url_for("akun")))
        flash("Nomor HP atau kata sandi salah.", "error")
    return render_template("login.html", hp=hp)


@app.route("/daftar", methods=["GET", "POST"])
def daftar():
    if session.get("user"):
        return redirect(url_for("akun"))
    f = request.form
    if request.method == "POST":
        u, err = t.daftar_pengguna(f.get("nama", ""), f.get("hp", ""),
                                   f.get("password", ""), f.get("ulang", ""))
        if err:
            flash(err, "error")
        else:
            session["user"] = u
            flash("Akun berhasil dibuat.", "ok")
            return redirect(next_aman(url_for("akun")))
    return render_template("daftar.html", form=f)


@app.route("/keluar")
def logout():
    session.pop("user", None)
    flash("Kamu sudah keluar.", "ok")
    return redirect(url_for("index"))


@app.route("/akun")
@login_required
def akun():
    u = session["user"]
    return render_template("akun.html", u=u, data=t.pesanan_by_hp(u["hp"]))


# ---------- Petugas & admin ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("pin") == t.PIN_ADMIN:
            session["admin"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") else url_for("admin"))
        flash("PIN salah.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin():
    return render_template("admin.html", r=t.ringkasan(), pesanan=t.semua_pesanan(),
                           kuota=t.ambil_kuota(), tutup=t.daftar_tutup(),
                           terjual_hari_ini=t.tiket_terjual(date.today().isoformat()))


@app.route("/admin/kuota", methods=["POST"])
@admin_required
def admin_kuota():
    t.atur_kuota(max(10, angka(request.form.get("kuota"), 5000)))
    flash("Kuota diperbarui.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/tutup", methods=["POST"])
@admin_required
def admin_tutup():
    tgl, aksi = request.form.get("tanggal", ""), request.form.get("aksi")
    try:
        date.fromisoformat(tgl)
    except ValueError:
        flash("Tanggal tidak valid.", "error")
        return redirect(url_for("admin"))
    (t.tutup_tanggal if aksi == "tutup" else t.buka_tanggal)(tgl)
    flash("Tanggal %s %s." % (tgl, "ditutup" if aksi == "tutup" else "dibuka"), "ok")
    return redirect(url_for("admin"))


@app.route("/admin/csv")
@admin_required
def admin_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["kode", "tanggal", "nama", "hp", "dewasa", "anak", "total", "metode", "status"])
    for d in t.semua_pesanan():
        w.writerow([d["kode"], d["tanggal_kunjungan"], d["nama"], d["hp"], d["dewasa"],
                    d["anak"], d["total"], d["metode"], d["status"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=laporan_pesanan.csv"})


@app.route("/scan", methods=["GET", "POST"])
@admin_required
def scan():
    hasil = None
    if request.method == "POST":
        ok, pesan_ = t.scan_tiket(request.form.get("kode", ""))
        hasil = {"ok": ok, "pesan": pesan_}
    return render_template("scan.html", hasil=hasil)


@app.errorhandler(404)
def tidak_ada(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)
