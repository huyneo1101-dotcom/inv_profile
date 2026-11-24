#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm thử trên lịch sử các họ luật tín hiệu coin rồi chốt loại nào được BẬT.

Chạy:
  python3 kiem_thu_coin.py                  # tải nến, chọn tham số trên đoạn dựng luật, kiểm đoạn sau, ghi data/coin-backtest.json
  python3 kiem_thu_coin.py --chi-thong-ke   # giữ NGUYÊN tham số đã chốt, chỉ tính lại số (hằng tuần); chỉ được TẮT, không tự BẬT
Tuỳ chọn: --du-lieu <thư mục đệm CSV> (mặc định /Users/Huy/Claude/TinHieuCoin/du-lieu nếu có, không thì
          thư mục tạm), --ra <file json>, --bao-cao <file markdown in bảng số>.

Chống nhìn trước: tín hiệu chỉ dùng nến đã đóng; bộ lọc ngày dùng nến ngày đã đóng trước lúc nến 4h đóng;
vào lệnh ở giá mở nến kế tiếp; kênh Donchian lấy N nến TRƯỚC nến tín hiệu; RSI tuần chỉ dùng tuần đã khép.
Chọn tham số CHỈ trên đoạn dựng luật (2017-08 → 2022-12-31), cùng một bộ cho cả 5 coin.
"""
from __future__ import annotations

import bisect
import datetime
import itertools
import json
import math
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coin_chung as cc  # noqa: E402

MOC_KIEM = int(datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
VO_CUC = 10 ** 15

# Ngưỡng BẬT (Huy chốt, cấm nới)
NGUONG = {"so_lenh_kiem": 30, "pf_kiem": 1.2, "r_tb_kiem": 0.10, "pf_dung": 1.1}
SO_LENH_TOI_THIEU_CHON = {"a": 50, "b": 50, "c": 50, "d": 8}

LUOI = {
    "a": {"N": [20, 40, 60, 120], "k": [2.0, 3.0, 4.0]},
    "b": {"L": [25, 30, 35], "k": [1.5, 2.5], "T": [1.5, 2.5]},
    "c": {"N": [20, 40, 60, 120], "k": [2.0, 3.0, 4.0]},
    "d": {"X": [0.15, 0.25, 0.35], "Y": [30, 35, 40, 45]},
}
CAC_LOAI = [("a", "LONG"), ("a", "SHORT"), ("b", "LONG"), ("b", "SHORT"),
            ("c", "LONG"), ("c", "SHORT"), ("d", "GOM")]


def to_hop(ho):
    g = LUOI[ho]
    ten = list(g)
    return [dict(zip(ten, v)) for v in itertools.product(*[g[k] for k in ten])]


def lang_gieng(ho, p):
    """Các tổ hợp lệch đúng một nấc ở đúng một tham số."""
    g = LUOI[ho]
    ra = []
    for k, ds in g.items():
        i = ds.index(p[k])
        for j in (i - 1, i + 1):
            if 0 <= j < len(ds):
                q = dict(p)
                q[k] = ds[j]
                ra.append(q)
    return ra


# ---------------------------------------------------------------- mô phỏng
def mo_phong_4h(coin, ctx, ho, huong, p, t0, t1):
    t, o, h, l, c, a = ctx["t"], ctx["o"], ctx["h"], ctx["l"], ctx["c"], ctx["atr"]
    n, dd, s = len(t), cc.DO_DAI["4h"], cc.dau(huong)
    ds = []
    i = bisect.bisect_left(t, t0)
    while i < n - 1 and t[i] < t1:
        if t[i + 1] >= t1:
            break
        if not cc.tin_hieu_4h(ctx, i, ho, huong, p):
            i += 1
            continue
        lenh = cc.tao_lenh(coin, ho, huong, p, c[i], a[i], t[i])
        vao = o[i + 1]
        if (vao - lenh["cat_lo"]) * s <= 0:      # giá mở đã vượt cắt lỗ: bỏ, như máy thật
            i += 1
            continue
        j = i + 1
        while True:
            kq = cc.soat_nen(lenh, o[j], h[j], l[j])
            if kq:
                ly, gia = kq
                break
            if cc.sau_nen_dong(lenh, t[j], h[j], l[j], a[j]):
                ly, gia = "het_han", c[j]
                break
            if j + 1 >= n or t[j + 1] >= t1:
                ly, gia = "het_doan", c[j]
                break
            j += 1
        t_ra = t[j] + dd
        so_ngay = (t_ra - t[i + 1]) / cc.NGAY
        if ly == "cat_lo" and lenh["cat_lo"] != lenh["cat_lo_0"]:
            ly = "cat_lo_duoi"
        ds.append({"coin": coin, "t_vao": t[i + 1], "t_ra": t_ra, "ly_do": ly, "ngay": so_ngay,
                   "gia_tc": c[i], "cat_lo_0": lenh["cat_lo_0"],
                   "R": cc.tinh_R(huong, vao, gia, lenh["cat_lo_0"], so_ngay)})
        i = j
    return ds


def mo_phong_gom(coin, ngay, p, t0, t1):
    t, o, h, l, c, a = ngay["t"], ngay["o"], ngay["h"], ngay["l"], ngay["c"], ngay["atr"]
    n = len(t)
    ds = []
    i = bisect.bisect_left(t, t0)
    while i < n - 1 and t[i] < t1:
        if t[i + 1] >= t1:
            break
        if not cc.tin_hieu_gom(ngay, i, p):
            i += 1
            continue
        lenh = cc.tao_lenh(coin, "d", "GOM", p, c[i], a[i], t[i])
        vao = o[i + 1]
        if vao <= lenh["cat_lo"]:
            i += 1
            continue
        j = i + 1
        while True:
            kq = cc.soat_nen(lenh, o[j], h[j], l[j])
            if kq:
                ly, gia = kq
                break
            if cc.sau_nen_dong(lenh, t[j], h[j], l[j], a[j]):
                ly, gia = "het_han", c[j]
                break
            if j + 1 >= n or t[j + 1] >= t1:
                ly, gia = "het_doan", c[j]
                break
            j += 1
        t_ra = t[j] + cc.NGAY
        so_ngay = (t_ra - t[i + 1]) / cc.NGAY
        ds.append({"coin": coin, "t_vao": t[i + 1], "t_ra": t_ra, "ly_do": ly, "ngay": so_ngay,
                   "R": cc.tinh_R("GOM", vao, gia, lenh["cat_lo_0"], so_ngay)})
        i = j
    return ds


def loi_suat_180(ngay, p, t0, t1):
    """Lợi suất 180 ngày sau: mua ở giá mở ngày kế, đo ở giá đóng ngày thứ 180. Vùng gom so với mọi ngày."""
    t, o, c = ngay["t"], ngay["o"], ngay["c"]
    vung, moi = [], []
    for j in range(bisect.bisect_left(t, t0), len(t) - cc.HAN_NGAY_D - 1):
        if t[j] >= t1 or t[j + cc.HAN_NGAY_D] + cc.NGAY > t1:
            break
        if ngay["ema200"][j] is None:
            continue
        r = c[j + cc.HAN_NGAY_D] / o[j + 1] - 1
        moi.append(r)
        if cc.tin_hieu_gom(ngay, j, p):
            vung.append(r)
    return vung, moi


# ---------------------------------------------------------------- thống kê
def thong_ke(ds):
    ds = sorted(ds, key=lambda x: x["t_ra"])
    R = [x["R"] for x in ds]
    n = len(R)
    if n == 0:
        return {"n": 0, "thang": None, "rTB": None, "pf": None, "sutR": None, "chuoiThua": 0, "tongR": 0.0, "t": None}
    duong = sum(r for r in R if r > 0)
    am = -sum(r for r in R if r <= 0)
    cong = dinh = sut = 0.0
    chuoi = dai = 0
    for r in R:
        cong += r
        dinh = max(dinh, cong)
        sut = max(sut, dinh - cong)
        chuoi = chuoi + 1 if r <= 0 else 0
        dai = max(dai, chuoi)
    tb = sum(R) / n
    sd = math.sqrt(sum((r - tb) ** 2 for r in R) / (n - 1)) if n > 1 else 0.0
    return {"n": n, "thang": sum(1 for r in R if r > 0) / n, "rTB": tb,
            "pf": (duong / am) if am > 0 else (999.0 if duong > 0 else 0.0),
            "sutR": sut, "chuoiThua": dai, "tongR": sum(R),
            "t": (tb / (sd / math.sqrt(n))) if sd > 0 else None,
            "ngayTB": sum(x["ngay"] for x in ds) / n}


def cam_giu(ctx, t0, t1):
    t, o, c = ctx["t"], ctx["o"], ctx["c"]
    i0 = bisect.bisect_left(t, t0)
    while i0 < len(t) and ctx["loc"][i0] == 0:
        i0 += 1
    i1 = bisect.bisect_left(t, t1) - 1
    if i0 >= len(t) or i1 <= i0:
        return None
    dinh, sut = o[i0], 0.0
    for x in c[i0:i1 + 1]:
        dinh = max(dinh, x)
        sut = max(sut, 1 - x / dinh)
    return {"tu": cc.ngay_iso(t[i0]), "den": cc.ngay_iso(t[i1]), "loi": c[i1] / o[i0] - 1, "sut": sut}


def lenh_mo_dong_thoi(ds):
    su_kien = sorted([(x["t_vao"], 1) for x in ds] + [(x["t_ra"], -1) for x in ds], key=lambda e: (e[0], e[1]))
    cur = top = 0
    for _, d in su_kien:
        cur += d
        top = max(top, cur)
    return top


# ---------------------------------------------------------------- dữ liệu
def nap(thu_muc, in_ra=print):
    now = int(time.time() * 1000)
    du, nguon = {}, {}
    for coin in cc.COINS:
        r4, n4 = cc.tai_toan_bo(coin, "4h", thu_muc, now, in_ra)
        r1, n1 = cc.tai_toan_bo(coin, "1d", thu_muc, now, in_ra)
        du[coin] = {"r4": r4, "r1": r1}
        nguon[coin] = {"4h": n4, "1d": n1, "tu": cc.ngay_iso(r4[0][0]), "den": cc.ngay_iso(r4[-1][0]),
                       "so4h": len(r4), "so1d": len(r1)}
        in_ra(f"  {coin}: {len(r4)} nến 4h, {len(r1)} nến ngày ({nguon[coin]['tu']} → {nguon[coin]['den']}), nguồn {n4}/{n1}")
    ngay_btc = cc.dung_ngay(du["BTC"]["r1"])
    for coin in cc.COINS:
        ng = ngay_btc if coin == "BTC" else cc.dung_ngay(du[coin]["r1"])
        du[coin]["ngay"] = ng
        du[coin]["c4"] = cc.dung_4h(du[coin]["r4"], ng, ngay_btc)
    return du, nguon


def chay(du, ho, huong, p, t0, t1):
    ds = []
    for coin in (cc.COIN_GOM if ho == "d" else cc.COINS):
        if ho == "d":
            ds += mo_phong_gom(coin, du[coin]["ngay"], p, t0, t1)
        else:
            ds += mo_phong_4h(coin, du[coin]["c4"], ho, huong, p, t0, t1)
    return ds


def khoa(ho, huong):
    return f"{ho}_{huong}"


def dong_tk(tk):
    if not tk["n"]:
        return "0 lệnh"
    return (f"{tk['n']} lệnh, thắng {cc.pct_vn(tk['thang'], 0)}, lãi TB {cc.r_vn(tk['rTB'])}, "
            f"hệ số {cc.so_vn(min(tk['pf'], 99), 2)}")


def danh_gia_cong(tk_d, tk_k, vung):
    """Trả (bật?, lý do một câu)."""
    thieu = []
    if tk_k["n"] < NGUONG["so_lenh_kiem"]:
        thieu.append(f"đoạn kiểm chỉ {tk_k['n']} lệnh (cần ≥ {NGUONG['so_lenh_kiem']})")
    if tk_k["n"] and tk_k["pf"] < NGUONG["pf_kiem"]:
        thieu.append(f"hệ số lợi nhuận đoạn kiểm {cc.so_vn(tk_k['pf'], 2)} (cần ≥ 1,2)")
    if tk_k["n"] and tk_k["rTB"] < NGUONG["r_tb_kiem"]:
        thieu.append(f"lãi TB đoạn kiểm {cc.r_vn(tk_k['rTB'])} (cần ≥ +0,10 R)")
    if not tk_d["n"] or tk_d["pf"] < NGUONG["pf_dung"]:
        thieu.append(f"hệ số đoạn dựng luật {cc.so_vn(tk_d['pf'] or 0, 2)} (cần ≥ 1,1)")
    if not vung:
        thieu.append("tham số kề bên sụp ở đoạn dựng luật")
    if thieu:
        return False, "Tắt vì " + "; ".join(thieu) + "."
    return True, f"Bật: đoạn kiểm {dong_tk(tk_k)}; đoạn dựng luật hệ số {cc.so_vn(tk_d['pf'], 2)}."


def dong_tin(tk_k, nam_dau, nam_cuoi):
    if not tk_k["n"]:
        return ""
    return (f"{nam_dau}-{nam_cuoi}: {tk_k['n']} lệnh, thắng {cc.pct_vn(tk_k['thang'], 0)}, "
            f"lãi TB {cc.r_vn(tk_k['rTB'])}")


# ---------------------------------------------------------------- chạy đầy đủ
def toi_uu(du, in_ra):
    ket = {}
    bang = {}
    for ho, huong in CAC_LOAI:
        k = khoa(ho, huong)
        hang = []
        for p in to_hop(ho):
            d = chay(du, ho, huong, p, 0, MOC_KIEM)
            kt = chay(du, ho, huong, p, MOC_KIEM, VO_CUC)
            hang.append({"p": p, "dung": thong_ke(d), "kiem": thong_ke(kt), "ds_kiem": kt, "ds_dung": d})
        bang[k] = hang
        du_mau = [x for x in hang if x["dung"]["n"] >= SO_LENH_TOI_THIEU_CHON[ho]]
        nhom = du_mau or hang
        chon = max(nhom, key=lambda x: (x["dung"]["rTB"] if x["dung"]["rTB"] is not None else -9))
        lg = [x for x in hang if x["p"] in lang_gieng(ho, chon["p"])]
        vung = all(x["dung"]["n"] > 0 and x["dung"]["pf"] >= 1.0 and x["dung"]["rTB"] >= 0 for x in lg)
        bat, ly = danh_gia_cong(chon["dung"], chon["kiem"], vung)
        ket[k] = {"chon": chon, "lang_gieng": lg, "vung": vung, "bat": bat, "ly": ly, "du_mau": bool(du_mau)}
        in_ra(f"{k}: chọn {chon['p']} | dựng {dong_tk(chon['dung'])} | kiểm {dong_tk(chon['kiem'])} | vững={vung} | {'BẬT' if bat else 'TẮT'}")
    # họ a và họ c gần như trùng nhau: cùng chiều chỉ giữ một, chọn theo đoạn dựng luật
    for huong in ("LONG", "SHORT"):
        ka, kc_ = khoa("a", huong), khoa("c", huong)
        if ket[ka]["bat"] and ket[kc_]["bat"]:
            bo = kc_ if ket[ka]["chon"]["dung"]["rTB"] >= ket[kc_]["chon"]["dung"]["rTB"] else ka
            giu = ka if bo == kc_ else kc_
            ket[bo]["bat"] = False
            ket[bo]["trung"] = giu
            ket[bo]["ly"] = (f"Tắt vì trùng với {giu} (hai họ gần như cùng tín hiệu); giữ {giu} vì lãi TB đoạn "
                             f"dựng luật cao hơn. Số của {bo}: " + ket[bo]["ly"])
    return ket, bang


def xuat_cfg(du, nguon, ket, bang, duong_ra):
    t_cuoi = max(du[c]["c4"]["t"][-1] for c in cc.COINS)
    nam_cuoi = cc.ngay_iso(t_cuoi)[:4]
    cfg = {
        "taoLuc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ghiChu": "Do kiem_thu_coin.py sinh. Tham số chọn trên đoạn dựng luật, số thống kê lấy ở đoạn kiểm (chưa dùng khi chọn).",
        "doanDung": ["2017-08-17", "2022-12-31"],
        "doanKiem": ["2023-01-01", cc.ngay_iso(t_cuoi)],
        "chiPhi": {"phiMoiChieu": cc.PHI, "truotMoiChieu": cc.TRUOT, "quaDemMoiNgay": cc.QUA_DEM_NGAY},
        "ruiRo": {"moiLenh": cc.RUI_RO, "tranTuongLai": cc.TRAN_TUONG_LAI, "tranMuaDut": cc.TRAN_MUA_DUT},
        "nguong": NGUONG,
        "luoi": LUOI,
        "soToHopDaThu": sum(len(to_hop(h)) for h, _ in CAC_LOAI),
        "nguonDuLieu": nguon,
        "camGiu": {c: {"dung": cam_giu(du[c]["c4"], 0, MOC_KIEM), "kiem": cam_giu(du[c]["c4"], MOC_KIEM, VO_CUC)}
                   for c in cc.COINS},
        "loai": {},
    }
    for ho, huong in CAC_LOAI:
        k = khoa(ho, huong)
        r = ket[k]
        tk_k = r["chon"]["kiem"]
        muc = {"ho": ho, "huong": huong, "ten": cc.TEN_HO[ho], "thamSo": r["chon"]["p"], "bat": r["bat"],
               "lyDo": r["ly"], "trungVoi": r.get("trung"), "vung": r["vung"], "duMauChon": r["du_mau"],
               "doanDung": r["chon"]["dung"], "doanKiem": tk_k,
               "dongTin": dong_tin(tk_k, 2023, nam_cuoi),
               "theoCoinKiem": {c: thong_ke([x for x in r["chon"]["ds_kiem"] if x["coin"] == c])
                                for c in (cc.COIN_GOM if ho == "d" else cc.COINS)},
               "langGieng": [{"thamSo": x["p"], "doanDung": x["dung"], "doanKiem": x["kiem"]} for x in r["lang_gieng"]]}
        if ho == "d":
            muc["loiSuat180"] = tinh_180(du, r["chon"]["p"])
        cfg["loai"][k] = muc
    bat = [k for k in cfg["loai"] if cfg["loai"][k]["bat"]]
    ds_bat = []
    for k in bat:
        ds_bat += ket[k]["chon"]["ds_kiem"]
    cfg["lenhMoDongThoiToiDaKiem"] = lenh_mo_dong_thoi(ds_bat) if ds_bat else 0
    cfg["gopLoaiBatKiem"] = thong_ke(ds_bat) if ds_bat else None
    with open(duong_ra, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1, sort_keys=False, default=_json_so)
    return cfg


def _json_so(x):
    return float(x)


def tinh_180(du, p):
    ra = {}
    for ten, t0, t1 in (("doanDung", 0, MOC_KIEM), ("doanKiem", MOC_KIEM, VO_CUC)):
        vung, moi = [], []
        so_dot = 0
        for coin in cc.COIN_GOM:
            v, m = loi_suat_180(du[coin]["ngay"], p, t0, t1)
            vung += v
            moi += m
        tb = (lambda x: sum(x) / len(x) if x else None)
        tv = sorted(vung)
        tm = sorted(moi)
        ra[ten] = {"soNgayTrongVung": len(vung), "loiTBVung": tb(vung), "trungViVung": tv[len(tv) // 2] if tv else None,
                   "tyLeAmVung": (sum(1 for x in vung if x < 0) / len(vung)) if vung else None,
                   "soNgayMoi": len(moi), "loiTBNgauNhien": tb(moi), "trungViNgauNhien": tm[len(tm) // 2] if tm else None,
                   "tyLeAmNgauNhien": (sum(1 for x in moi if x < 0) / len(moi)) if moi else None}
    return ra


# ---------------------------------------------------------------- bảng markdown cho báo cáo
def f2(x, le=2):
    return "—" if x is None else cc.so_vn(min(x, 99) if le == 2 else x, le)


def hang_md(nhan, tk):
    if not tk["n"]:
        return f"| {nhan} | 0 | — | — | — | — | — | — |"
    return (f"| {nhan} | {tk['n']} | {cc.pct_vn(tk['thang'], 0)} | {cc.r_vn(tk['rTB'])} | {f2(tk['pf'])} | "
            f"{cc.so_vn(tk['sutR'], 1)} | {tk['chuoiThua']} | {cc.so_vn(tk['tongR'], 1)} |")


def bao_cao_md(cfg, bang):
    out = []
    dau_bang = "| Tổ hợp | Lệnh | Thắng | Lãi TB | Hệ số | Sụt tối đa (R) | Chuỗi thua | Tổng R |\n|---|---|---|---|---|---|---|---|"
    for k, m in cfg["loai"].items():
        out.append(f"\n### Loại {k}: {m['ten']}\n")
        out.append(f"Tham số chốt: `{json.dumps(m['thamSo'])}` · vững: {'có' if m['vung'] else 'KHÔNG'} · "
                   f"**{'BẬT' if m['bat'] else 'TẮT'}** · {m['lyDo']}\n")
        out.append(dau_bang)
        out.append(hang_md("Chốt, đoạn dựng luật", m["doanDung"]))
        out.append(hang_md("Chốt, đoạn kiểm", m["doanKiem"]))
        if m["doanKiem"]["n"] and m["doanKiem"].get("t") is not None:
            out.append(f"\nThống kê t của lãi TB đoạn kiểm: {cc.so_vn(m['doanKiem']['t'], 2)}.")
        out.append("\nTheo coin, đoạn kiểm: " + "; ".join(
            f"{c} {tk['n']} lệnh {cc.r_vn(tk['rTB']) if tk['n'] else ''}" for c, tk in m["theoCoinKiem"].items()) + ".")
        if "loiSuat180" in m:
            for ten, v in m["loiSuat180"].items():
                out.append(f"\nLợi suất 180 ngày, {ten}: {v['soNgayTrongVung']} ngày trong vùng, TB "
                           f"{f2(v['loiTBVung'] and v['loiTBVung']*100, 1)}% (trung vị {f2(v['trungViVung'] and v['trungViVung']*100, 1)}%, "
                           f"âm {f2(v['tyLeAmVung'] and v['tyLeAmVung']*100, 0)}%) so với mua ngẫu nhiên {v['soNgayMoi']} ngày TB "
                           f"{f2(v['loiTBNgauNhien'] and v['loiTBNgauNhien']*100, 1)}% (âm {f2(v['tyLeAmNgauNhien'] and v['tyLeAmNgauNhien']*100, 0)}%).")
        out.append("\nToàn lưới 12 tổ hợp (D = đoạn dựng luật, K = đoạn kiểm):\n")
        out.append("| Tham số | D lệnh | D lãi TB | D hệ số | K lệnh | K lãi TB | K hệ số |\n|---|---|---|---|---|---|---|")
        for x in bang[k]:
            d, kk = x["dung"], x["kiem"]
            out.append(f"| `{json.dumps(x['p'])}` | {d['n']} | {cc.r_vn(d['rTB']) if d['n'] else '—'} | {f2(d['pf'])} | "
                       f"{kk['n']} | {cc.r_vn(kk['rTB']) if kk['n'] else '—'} | {f2(kk['pf'])} |")
    out.append("\n### Cầm giữ cùng giai đoạn\n\n| Coin | Dựng luật: lãi | Dựng luật: sụt | Kiểm: lãi | Kiểm: sụt |\n|---|---|---|---|---|")
    for c, v in cfg["camGiu"].items():
        d, kk = v["dung"], v["kiem"]
        out.append(f"| {c} | {cc.pct_vn(d['loi'], 0) if d else '—'} | {cc.pct_vn(d['sut'], 0) if d else '—'} | "
                   f"{cc.pct_vn(kk['loi'], 0) if kk else '—'} | {cc.pct_vn(kk['sut'], 0) if kk else '—'} |")
    return "\n".join(out)


# ---------------------------------------------------------------- chỉ thống kê (tham số cố định)
def chi_thong_ke(du, nguon, duong_ra, in_ra):
    with open(duong_ra, encoding="utf-8") as f:
        cfg = json.load(f)
    t_cuoi = max(du[c]["c4"]["t"][-1] for c in cc.COINS)
    nam_cuoi = cc.ngay_iso(t_cuoi)[:4]
    ds_bat = []
    for k, m in cfg["loai"].items():
        ho, huong, p = m["ho"], m["huong"], m["thamSo"]
        d = chay(du, ho, huong, p, 0, MOC_KIEM)
        kt = chay(du, ho, huong, p, MOC_KIEM, VO_CUC)
        m["doanDung"], m["doanKiem"] = thong_ke(d), thong_ke(kt)
        m["dongTin"] = dong_tin(m["doanKiem"], 2023, nam_cuoi)
        m["theoCoinKiem"] = {c: thong_ke([x for x in kt if x["coin"] == c]) for c in (cc.COIN_GOM if ho == "d" else cc.COINS)}
        if ho == "d":
            m["loiSuat180"] = tinh_180(du, p)
        if m["bat"]:
            ok, ly = danh_gia_cong(m["doanDung"], m["doanKiem"], m.get("vung", False))
            if not ok:   # chỉ được TẮT tự động; BẬT lại phải chạy đầy đủ và người soát
                m["bat"] = False
                m["lyDo"] = f"Tắt tự động {cc.ngay_iso(t_cuoi)} khi cập nhật số hằng tuần. " + ly
            else:
                ds_bat += kt
        in_ra(f"{k}: {'BẬT' if m['bat'] else 'TẮT'} | kiểm {dong_tk(m['doanKiem'])}")
    cfg["doanKiem"] = ["2023-01-01", cc.ngay_iso(t_cuoi)]
    cfg["nguonDuLieu"] = nguon
    cfg["capNhatSoLuc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cfg["camGiu"] = {c: {"dung": cam_giu(du[c]["c4"], 0, MOC_KIEM), "kiem": cam_giu(du[c]["c4"], MOC_KIEM, VO_CUC)}
                     for c in cc.COINS}
    cfg["lenhMoDongThoiToiDaKiem"] = lenh_mo_dong_thoi(ds_bat) if ds_bat else 0
    cfg["gopLoaiBatKiem"] = thong_ke(ds_bat) if ds_bat else None
    with open(duong_ra, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1, default=_json_so)
    return cfg


def main(argv):
    def lay(ten, mac_dinh):
        return argv[argv.index(ten) + 1] if ten in argv else mac_dinh
    goc = os.path.dirname(os.path.abspath(__file__))
    mac_dinh_dem = "/Users/Huy/Claude/TinHieuCoin/du-lieu"
    thu_muc = lay("--du-lieu", os.environ.get("COIN_DU_LIEU") or (
        mac_dinh_dem if os.path.isdir(mac_dinh_dem) else os.path.join(tempfile.gettempdir(), "nen-coin")))
    duong_ra = lay("--ra", os.path.join(goc, "data", "coin-backtest.json"))
    print(f"Đệm nến: {thu_muc}")
    du, nguon = nap(thu_muc)
    if "--chi-thong-ke" in argv:
        chi_thong_ke(du, nguon, duong_ra, print)
        print(f"Đã cập nhật số (tham số giữ nguyên): {duong_ra}")
        return 0
    ket, bang = toi_uu(du, print)
    cfg = xuat_cfg(du, nguon, ket, bang, duong_ra)
    print(f"Đã ghi {duong_ra}")
    md = lay("--bao-cao", None)
    if md:
        with open(md, "w", encoding="utf-8") as f:
            f.write(bao_cao_md(cfg, bang))
        print(f"Bảng số: {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
