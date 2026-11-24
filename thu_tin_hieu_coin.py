#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ca thử cho tin_hieu_coin.danh_gia và coin_chung. Chạy: python3 thu_tin_hieu_coin.py (mã 0 = đạt).

Dữ liệu nến dựng tay, không gọi mạng, không gửi Zalo. Mỗi chốt chặn có ca PHẢI CHẶN đi kèm ca PHẢI BÁO
cùng dữ liệu (để chứng minh ca chặn không đạt nhờ máy im lặng vô điều kiện).
Thêm: python3 thu_tin_hieu_coin.py --day-du  -> phát lại danh_gia trên nến thật đã đệm (nếu có thư mục đệm)
và so từng lệnh với máy kiểm thử lịch sử.
"""
from __future__ import annotations

import copy
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["VON_USDT"] = "380"   # vốn giả định của bộ ca thử (số trong ca tính theo mức này)
import coin_chung as cc  # noqa: E402
import tin_hieu_coin as th  # noqa: E402

H4 = cc.DO_DAI["4h"]
D = cc.NGAY
T0 = 1767225600000           # 2026-01-01 00:00 UTC
N4 = 200                     # số nến 4h dựng sẵn trước nến tín hiệu
K = N4 - 1                   # chỉ số nến tín hiệu

CA = []


def ca(ten, dieu_kien, ghi_chu=""):
    CA.append((ten, bool(dieu_kien)))
    print(("ĐẠT   " if dieu_kien else "TRƯỢT ") + ten + (f"  [{ghi_chu}]" if ghi_chu and not dieu_kien else ""))


def cfg_thu(**bat):
    p = {"N": 120, "k": 4.0}
    loai = {}
    for k, ho, huong, tham in (("a_LONG", "a", "LONG", p), ("a_SHORT", "a", "SHORT", p),
                               ("b_LONG", "b", "LONG", {"L": 35, "k": 2.5, "T": 2.5}),
                               ("b_SHORT", "b", "SHORT", {"L": 35, "k": 1.5, "T": 1.5}),
                               ("c_LONG", "c", "LONG", p), ("c_SHORT", "c", "SHORT", p),
                               ("d_GOM", "d", "GOM", {"X": 0.35, "Y": 35})):
        loai[k] = {"ho": ho, "huong": huong, "thamSo": tham, "bat": bool(bat.get(k, False)),
                   "dongTin": "2023-2026: 157 lệnh, thắng 43%, lãi TB +0,29 R",
                   "doanKiem": {"n": 157, "rTB": 0.29, "pf": 1.85, "thang": 0.43}}
    return {"loai": loai}


def ngay_rows(chieu, so=280):
    """Nến ngày từ T0-240 ngày; chieu=+1 giá đi lên (trên EMA200), -1 đi xuống (dưới EMA200)."""
    ra = []
    for d in range(so):
        c = 100 + 0.5 * d if chieu > 0 else 300 - 0.5 * d
        ra.append((T0 - 240 * D + d * D, c, c + 1, c - 1, c))
    return ra


def h4_rows(kieu="pha_len", them=0):
    """N4 nến phẳng quanh 100, nến thứ K là nến tín hiệu; 'them' nến sau đó đi ngang ở giá đóng của nến K."""
    ra = [(T0 + i * H4, 100.0, 101.0, 99.0, 100.0) for i in range(K)]
    if kieu == "pha_len":
        ra.append((T0 + K * H4, 100.0, 106.0, 99.5, 105.0))
    elif kieu == "pha_xuong":
        ra.append((T0 + K * H4, 100.0, 100.5, 94.0, 95.0))
    else:
        ra.append((T0 + K * H4, 100.0, 101.0, 99.0, 100.0))
    gia = ra[-1][4]
    for j in range(1, them + 1):
        ra.append((T0 + (K + j) * H4, gia, gia + 0.2, gia - 0.2, gia))
    return ra


def dong_K():
    """Giờ ngay sau khi nến K đóng (1 phút)."""
    return T0 + (K + 1) * H4 + 60_000


def nen(coin_4h, ngay_coin=+1, ngay_btc=+1):
    """Bộ nến cho mọi coin: coin trong coin_4h dùng kiểu được chỉ định, coin khác đi phẳng."""
    n4, n1 = {}, {}
    for coin in cc.COINS:
        n4[coin] = coin_4h.get(coin) or h4_rows("phang")
        n1[coin] = ngay_rows(ngay_btc if coin == "BTC" else ngay_coin)
    return n4, n1


ST = {"batDau": 1, "nenDaXet": {}, "lenhMo": {}, "baoDoiCatLo": {}, "lichSu": [], "boLo": []}


def loai_tin(tins, loai=None, coin=None):
    return [t for t in tins if (loai is None or t["loai"] == loai) and (coin is None or t["coin"] == coin)]


# ---------------------------------------------------------------- 1. không vào trùng
def ca_khong_vao_trung():
    n4, n1 = nen({"ETH": h4_rows("pha_len", them=1)})
    cfg = cfg_thu(c_LONG=True)
    bg = dong_K()
    tins, _ = th.danh_gia(n4, n1, ST, cfg, bg)
    ca("PHẢI BÁO: ETH phá đỉnh, chưa có lệnh -> 01 tin vào LONG", len(loai_tin(tins, "vao", "ETH")) == 1)
    dang_mo = copy.deepcopy(ST)
    lenh = cc.tao_lenh("ETH", "c", "LONG", {"N": 120, "k": 4.0}, 100.0, 2.0, T0 + (K - 5) * H4)
    lenh.update({"loai": "c_LONG", "nen_cuoi": T0 + (K - 5) * H4, "cat_lo": 80.0, "cat_lo_0": 80.0})
    dang_mo["lenhMo"]["ETH|LONG"] = lenh
    tins, moi = th.danh_gia(n4, n1, dang_mo, cfg, bg)
    ca("PHẢI CHẶN: đang mở ETH LONG thì tín hiệu mới không vào trùng", not loai_tin(tins, "vao", "ETH"))
    ca("PHẢI CHẶN: lệnh cũ giữ nguyên, không bị thay", moi["lenhMo"]["ETH|LONG"]["t_tin_hieu"] == lenh["t_tin_hieu"])
    tins2, _ = th.danh_gia(n4, n1, th.danh_gia(n4, n1, ST, cfg, bg)[1], cfg, bg + 60_000)
    ca("PHẢI CHẶN: chạy lại cùng nến sau khi đã vào -> không vào lần hai", not loai_tin(tins2, "vao"))


# ---------------------------------------------------------------- 2. nến chưa đóng
def ca_nen_chua_dong():
    cfg = cfg_thu(c_LONG=True)
    n4, n1 = nen({"ETH": h4_rows("pha_len")})
    bg = T0 + K * H4 + 2 * cc.GIO          # nến K mới chạy được 2 giờ, đã vọt qua đỉnh
    tins, _ = th.danh_gia(n4, n1, ST, cfg, bg)
    ca("PHẢI CHẶN: nến 4h đang chạy vượt đỉnh -> chưa phát tín hiệu", not loai_tin(tins, "vao"))
    tins, _ = th.danh_gia(n4, n1, ST, cfg, T0 + (K + 1) * H4 + 60_000)
    ca("PHẢI BÁO: cùng nến đó sau khi đóng -> phát tín hiệu", len(loai_tin(tins, "vao", "ETH")) == 1)


# ---------------------------------------------------------------- 3. bộ lọc xu hướng cấm Short
def ca_loc_short():
    cfg = cfg_thu(a_SHORT=True, c_SHORT=True)
    bg = dong_K()
    n4, n1 = nen({"BTC": h4_rows("pha_xuong", 1), "ETH": h4_rows("pha_xuong", 1)}, ngay_coin=+1, ngay_btc=+1)
    tins, _ = th.danh_gia(n4, n1, ST, cfg, bg)
    ca("PHẢI CHẶN: thủng đáy nhưng giá ngày trên EMA200 -> không Short", not loai_tin(tins, "vao"))
    n4, n1 = nen({"BTC": h4_rows("pha_xuong", 1), "ETH": h4_rows("pha_xuong", 1)}, ngay_coin=-1, ngay_btc=-1)
    tins, _ = th.danh_gia(n4, n1, ST, cfg, bg)
    ca("PHẢI BÁO: thủng đáy và giá ngày dưới EMA200 -> Short BTC và ETH", len(loai_tin(tins, "vao")) == 2)
    cfg = cfg_thu(c_SHORT=True)
    n4, n1 = nen({"ETH": h4_rows("pha_xuong", 1)}, ngay_coin=-1, ngay_btc=+1)
    tins, _ = th.danh_gia(n4, n1, ST, cfg, bg)
    ca("PHẢI CHẶN: họ c, ETH dưới EMA200 nhưng BTC trên -> không Short ETH", not loai_tin(tins, "vao"))
    cfg = cfg_thu(c_LONG=True)
    n4, n1 = nen({"ETH": h4_rows("pha_len", 1)}, ngay_coin=-1, ngay_btc=-1)
    tins, _ = th.danh_gia(n4, n1, ST, cfg, bg)
    ca("PHẢI CHẶN: phá đỉnh nhưng giá ngày dưới EMA200 -> không Long", not loai_tin(tins, "vao"))


# ---------------------------------------------------------------- 4. loại TẮT không bao giờ nhắn
def ca_loai_tat():
    n4, n1 = nen({c: h4_rows("pha_len", 1) for c in cc.COINS})
    tat_het = cfg_thu()
    st = copy.deepcopy(ST)
    tong = []
    for buoc in range(4):
        tins, st = th.danh_gia(n4, n1, st, tat_het, dong_K() + buoc * 15 * 60_000)
        tong += tins
    ca("PHẢI CHẶN: mọi loại TẮT, 5 coin cùng phá đỉnh, 4 lượt -> không một tin", not tong)
    tins, _ = th.danh_gia(n4, n1, ST, cfg_thu(c_SHORT=True, a_SHORT=True, b_LONG=False), dong_K())
    ca("PHẢI CHẶN: chỉ bật Short, tín hiệu là Long -> không tin", not tins)
    tins, _ = th.danh_gia(n4, n1, ST, cfg_thu(c_LONG=True), dong_K())
    ca("PHẢI BÁO: bật c_LONG cùng dữ liệu -> có tin vào", len(loai_tin(tins, "vao")) == 5)
    hong = cfg_thu(c_LONG=True)
    hong["loai"]["c_LONG"]["bat"] = "false"          # cấu hình hỏng kiểu chuỗi: không được hiểu là bật
    tins, _ = th.danh_gia(n4, n1, ST, hong, dong_K())
    ca("PHẢI CHẶN: cờ bật ghi sai kiểu (chuỗi) -> coi là tắt", not tins)


# ---------------------------------------------------------------- 5. chạm cắt lỗ chỉ nhắn 1 lần
def lenh_mo(coin="BTC", huong="LONG", gia=105.0, cat_lo=95.0, t_tin_hieu=None, ho="c"):
    t_tin_hieu = T0 + K * H4 if t_tin_hieu is None else t_tin_hieu
    tham = {"L": 35, "k": 4.0, "T": 2.5} if ho == "b" else {"N": 120, "k": 4.0}
    lenh = cc.tao_lenh(coin, ho, huong, tham, gia, 2.5, t_tin_hieu)
    lenh.update({"loai": f"{ho}_{huong}", "nen_cuoi": t_tin_hieu, "cat_lo": cat_lo, "cat_lo_0": cat_lo})
    st = copy.deepcopy(ST)
    st["lenhMo"][f"{coin}|{huong}"] = lenh
    for c in cc.COINS:
        st["nenDaXet"][f"{c}|4h"] = T0 + (K + 10) * H4
        st["nenDaXet"][f"{c}|1d"] = T0 + 40 * D
    return st


def ca_cat_lo_mot_lan():
    cfg = cfg_thu(c_LONG=True)
    r = h4_rows("pha_len") + [(T0 + (K + 1) * H4, 105.0, 105.5, 90.0, 92.0)]   # nến sau thủng cắt lỗ 95
    n4, n1 = nen({"BTC": r})
    st = lenh_mo()
    bg = T0 + (K + 2) * H4 + 60_000
    tins, moi = th.danh_gia(n4, n1, st, cfg, bg)
    dong = loai_tin(tins, "dong", "BTC")
    ca("PHẢI BÁO: nến đã đóng thủng cắt lỗ -> 01 tin đóng", len(dong) == 1)
    ca("PHẢI BÁO: tin đóng ghi lãi/lỗ bằng USDT và % vốn", dong and ("lãi " in dong[0]["text"] or "lỗ " in dong[0]["text"]) and "% vốn" in dong[0]["text"]
       and "USDT" in dong[0]["text"] and "95,00 USD" in dong[0]["text"])
    ca("PHẢI BÁO: chạm đúng cắt lỗ đã nhắn -> tin báo sàn đã tự đóng, không bắt đóng tay",
       dong and "đã tự đóng" in dong[0]["text"] and "ĐÓNG TAY" not in dong[0]["text"])
    r_gap = h4_rows("pha_len") + [(T0 + (K + 1) * H4, 90.0, 91.0, 88.0, 89.0)]   # giá mở đã nhảy qua cắt lỗ
    n4g, n1g = nen({"BTC": r_gap})
    tg, _ = th.danh_gia(n4g, n1g, lenh_mo(), cfg, bg)
    ca("PHẢI BÁO: giá mở nhảy qua cắt lỗ -> tin bảo kiểm tra sàn, không nói sàn đã đóng đúng mức",
       loai_tin(tg, "dong") and "NHẢY QUA" in loai_tin(tg, "dong")[0]["text"])
    R_mong = cc.tinh_R("LONG", 105.0, 95.0, 95.0, 4 / 24)     # vào đầu nến K+1, ra hết nến K+1 = 4 giờ
    ca("PHẢI BÁO: R ghi trong lịch sử khớp công thức", abs(moi["lichSu"][-1]["R"] - round(R_mong, 3)) < 1e-9,
       f"{moi['lichSu'][-1]['R']} vs {R_mong}")
    tong = []
    for buoc in range(1, 4):
        tins, moi = th.danh_gia(n4, n1, moi, cfg, bg + buoc * 15 * 60_000)
        tong += loai_tin(tins, "dong")
    ca("PHẢI CHẶN: 3 lượt sau giá vẫn dưới cắt lỗ -> không nhắn lại", not tong)
    # 15 phút: nến đang chạy chọc xuống dưới cắt lỗ thì báo ngay, không chờ nến đóng
    r2 = h4_rows("pha_len") + [(T0 + (K + 1) * H4, 105.0, 105.5, 94.0, 96.0)]
    n4, n1 = nen({"BTC": r2})
    tins, moi = th.danh_gia(n4, n1, lenh_mo(), cfg, T0 + (K + 1) * H4 + 30 * 60_000)
    ca("PHẢI BÁO: nến 4h đang chạy chạm cắt lỗ -> báo đóng ngay", len(loai_tin(tins, "dong", "BTC")) == 1)
    tins, _ = th.danh_gia(n4, n1, moi, cfg, T0 + (K + 1) * H4 + 45 * 60_000)
    ca("PHẢI CHẶN: lượt 15 phút sau cùng nến -> không nhắn lại", not loai_tin(tins, "dong"))
    # nến chạm cả cắt lỗ lẫn mục tiêu (họ b) -> tính là cắt lỗ
    st = lenh_mo(ho="b")
    st["lenhMo"]["BTC|LONG"]["muc_tieu"] = 110.0
    r3 = h4_rows("pha_len") + [(T0 + (K + 1) * H4, 105.0, 112.0, 94.0, 100.0)]
    n4, n1 = nen({"BTC": r3})
    tins, moi = th.danh_gia(n4, n1, st, cfg_thu(b_LONG=True), T0 + (K + 2) * H4 + 60_000)
    ca("PHẢI CHẶN: nến chạm cả cắt lỗ lẫn mục tiêu -> tính dính cắt lỗ, không tính chốt lời",
       moi["lichSu"] and moi["lichSu"][-1]["lyDo"] == "cat_lo")


# ---------------------------------------------------------------- 6. cỡ lệnh
def ca_co_lenh():
    a = cc.co_lenh(100.0, 95.0)
    ca("PHẢI BÁO: cắt lỗ cách 5% -> vị thế 20% vốn, mất đúng 1%", abs(a["gia_tri"] - 0.2) < 1e-12 and abs(a["rui_ro"] - 0.01) < 1e-12)
    b = cc.co_lenh(100.0, 99.9)
    ca("PHẢI CHẶN: cắt lỗ cách 0,1% -> vị thế không vượt 3 lần vốn", b["gia_tri"] <= 3.0 + 1e-12 and b["cham_tran"])
    ca("PHẢI CHẶN: khi chạm trần, rủi ro thực < 1% (không âm thầm vượt)", b["rui_ro"] <= 0.01 + 1e-12)
    g = cc.co_lenh(100.0, 99.0, mua_dut=True)
    ca("PHẢI CHẶN: mua đứt không vượt 1 lần vốn", g["gia_tri"] <= 1.0 + 1e-12)
    for kc in (0.003, 0.01, 0.02, 0.05, 0.1, 0.3):
        x = cc.co_lenh(50.0, 50.0 * (1 - kc))
        if not (x["rui_ro"] <= 0.01 + 1e-12 and x["gia_tri"] <= 3.0 + 1e-12 and (x["cham_tran"] or abs(x["rui_ro"] - 0.01) < 1e-12)):
            ca(f"PHẢI CHẶN: cỡ lệnh sai ở khoảng cắt lỗ {kc}", False)
            return
    ca("PHẢI BÁO: lưới khoảng cắt lỗ 0,3%-30% đều đúng 1% hoặc chạm trần", True)
    R = cc.tinh_R("LONG", 100.0, 95.0 / (1 - cc.TRUOT) * (1 + cc.TRUOT) / (1 + cc.TRUOT), 95.0, 0)
    ca("PHẢI BÁO: ra đúng ở cắt lỗ -> lỗ khoảng 1R cộng phí", -1.1 < R < -0.99, f"R={R}")
    # tin vào lệnh in đúng % vốn của cỡ lệnh
    n4, n1 = nen({"ETH": h4_rows("pha_len", 1)})
    tins, moi = th.danh_gia(n4, n1, ST, cfg_thu(c_LONG=True), dong_K())
    t = loai_tin(tins, "vao", "ETH")[0]["text"]
    l = moi["lenhMo"]["ETH|LONG"]
    co = cc.co_lenh(l["gia_tc"], l["cat_lo"])
    san = cc.lenh_san("ETH", l["gia_tc"], l["cat_lo"])
    ca("PHẢI BÁO: tin vào in số coin, USDT, ký quỹ x3 và % vốn rủi ro thật của cỡ lệnh",
       f"{cc.so_vn(san['so_luong'], san['le'])} ETH" in t and f"ký quỹ {cc.so_vn(san['ky_quy_usdt'], 1)} USDT" in t
       and f"= {cc.pct_vn(san['rui_ro_that'], 2)} vốn" in t and san["rui_ro_that"] <= cc.RUI_RO + 1e-9
       and co["gia_tri"] <= cc.TRAN_TUONG_LAI, t)


# ---------------------------------------------------------------- 7. dời cắt lỗ: chỉ ở mốc 07:00 VN, ≥ 0,5%
def nen_tang(so):
    """Sau nến K (mở 04:00 UTC), BTC tăng đều 3 USD mỗi nến 4h. Nến K+4, K+10, K+16 mở 20:00 UTC (đóng 07:00 VN)."""
    r = h4_rows("pha_len")
    gia = 105.0
    for j in range(1, so + 1):
        r.append((T0 + (K + j) * H4, gia, gia + 3.2, gia - 0.3, gia + 3.0))
        gia += 3.0
    return r


def ca_doi_cat_lo():
    ca("PHẢI BÁO: nến K+4 là nến đóng 00:00 UTC", cc.la_moc_doi(T0 + (K + 4) * H4) and not cc.la_moc_doi(T0 + (K + 3) * H4))
    # đơn vị: sau_nen_dong
    def l0():
        x = cc.tao_lenh("BTC", "c", "LONG", {"N": 120, "k": 4.0}, 100.0, 1.0, 0)
        x["cat_lo"] = 90.0
        x["cuc_tri"] = 90.0          # đỉnh từ lúc vào đặt thấp để mức mới = h − 4 × ATR
        return x
    moc = T0 + (K + 4) * H4
    x = l0(); cc.sau_nen_dong(x, moc + H4, 120.0, 99.0, 1.0)
    ca("PHẢI CHẶN: nến không phải mốc 07:00 VN -> không dời dù đỉnh vọt", x["cat_lo"] == 90.0 and x["cuc_tri"] == 120.0)
    x = l0(); cc.sau_nen_dong(x, moc, 94.4, 93.0, 1.0)       # mức mới 90,4: tốt hơn 0,4 < 0,5% × 100
    ca("PHẢI CHẶN: mức mới chỉ tốt hơn 0,4% giá tham chiếu -> giữ nguyên", x["cat_lo"] == 90.0)
    x = l0(); cc.sau_nen_dong(x, moc, 94.6, 93.0, 1.0)       # mức mới 90,6: tốt hơn 0,6
    ca("PHẢI BÁO: tốt hơn ≥ 0,5% ở mốc 07:00 VN -> dời", abs(x["cat_lo"] - 90.6) < 1e-9, str(x["cat_lo"]))
    x = l0(); cc.sau_nen_dong(x, moc + H4, 130.0, 99.0, 1.0); cc.sau_nen_dong(x, moc + 6 * H4, 101.0, 99.0, 2.0)
    ca("PHẢI BÁO: đỉnh giữa ngày vẫn được nhớ, mốc sau dùng ATR của nến mốc", abs(x["cat_lo"] - 122.0) < 1e-9, str(x["cat_lo"]))
    s = cc.tao_lenh("BTC", "c", "SHORT", {"N": 120, "k": 4.0}, 100.0, 1.0, 0)
    s["cat_lo"] = 110.0; cc.sau_nen_dong(s, moc, 101.0, 95.0, 1.0)
    ca("PHẢI BÁO: Short dời xuống = đáy + k×ATR", abs(s["cat_lo"] - 99.0) < 1e-9, str(s["cat_lo"]))
    # tích hợp: 6 lượt trong ~26 giờ, chỉ dời ở lượt ngay sau 07:00 VN
    cfg = cfg_thu(c_LONG=True)
    st = lenh_mo(cat_lo=85.0)
    lan, cl = [], []
    for so in (2, 4, 6, 8, 10, 11):
        n4, n1 = nen({"BTC": nen_tang(so)})
        tins, st = th.danh_gia(n4, n1, st, cfg, T0 + (K + so + 1) * H4 + 60_000)
        d = loai_tin(tins, "doi_cat_lo")
        lan.append(len(d))
        cl.append(st["lenhMo"]["BTC|LONG"]["cat_lo"])
        if d:
            ca(f"PHẢI BÁO: tin dời in đúng cắt lỗ trong state ({so})", cc.gia_vn(cl[-1]) in d[0]["text"], d[0]["text"])
    ca("PHẢI CHẶN: chỉ dời ở lượt sau mốc 07:00 VN, tối đa 01 tin/coin/ngày", lan == [0, 1, 0, 0, 1, 0], str(lan))
    ca("PHẢI CHẶN: giữa hai mốc cắt lỗ trong state đứng yên (= mức đã nhắn = mức trên sàn)",
       cl[1] == cl[2] == cl[3] and cl[4] == cl[5] and cl[4] > cl[1] > 85.0, str(cl))
    # cắt lỗ vừa dời ở nến mốc mà nến đang chạy đã chạm mức mới (bot chạy trễ): bắt đóng tay
    r = nen_tang(4) + [(T0 + (K + 5) * H4, 117.0, 117.5, 100.0, 101.0)]
    n4, n1 = nen({"BTC": r})
    tins, _ = th.danh_gia(n4, n1, lenh_mo(cat_lo=85.0), cfg, T0 + (K + 5) * H4 + 2 * cc.GIO)
    d = loai_tin(tins, "dong")
    ca("PHẢI BÁO: chạm cắt lỗ mới chưa kịp nhắn -> tin bảo ĐÓNG TAY", d and "ĐÓNG TAY" in d[0]["text"], str([t["text"] for t in tins]))


# ---------------------------------------------------------------- 7b. cỡ lệnh theo sàn (vốn USDT, bước số lượng)
def ca_lenh_san():
    rd = random.Random(3)
    nho_hon_toi_thieu, vuot_1, sai_bo_qua, tong = [], [], [], 0
    for coin, (buoc, toi_thieu) in cc.BUOC_SAN.items():
        for _ in range(400):
            gia = {"BTC": 90000, "ETH": 3000, "SOL": 150, "BNB": 600, "XRP": 2.2}[coin] * rd.uniform(0.3, 3)
            kc = rd.uniform(0.003, 0.25)
            x = cc.lenh_san(coin, gia, gia * (1 - kc))
            tong += 1
            if x["so_luong"] + 1e-12 < buoc or x["gia_tri_usdt"] + 1e-9 < toi_thieu:
                nho_hon_toi_thieu.append((coin, gia, kc, x["so_luong"]))
            if not x["nang_len_toi_thieu"] and x["rui_ro_that"] > 0.01 + 1e-12:
                vuot_1.append((coin, gia, kc, x["rui_ro_that"]))
            if x["bo_qua"] != (x["rui_ro_that"] > 0.015 or x["gia_tri_usdt"] > 3 * cc.VON_USDT + 1e-9):
                sai_bo_qua.append((coin, gia, kc))
    ca(f"PHẢI CHẶN: {tong} tổ hợp giá/cắt lỗ, không bao giờ ra số lượng dưới tối thiểu sàn", not nho_hon_toi_thieu,
       str(nho_hon_toi_thieu[:3]))
    ca("PHẢI CHẶN: làm tròn theo bước sàn không làm rủi ro vượt 1%", not vuot_1, str(vuot_1[:3]))
    ca("PHẢI CHẶN: cờ khuyên bỏ qua bật đúng khi rủi ro thật > 1,5%", not sai_bo_qua, str(sai_bo_qua[:3]))
    x = cc.lenh_san("ETH", 3000.0, 2850.0)               # cắt lỗ 5%: 76 USDT lý thuyết
    ca("PHẢI BÁO: ETH 3.000, cắt lỗ 5% -> 0,025 ETH, 75 USDT, ký quỹ 25 USDT, mất 3,75 USDT",
       abs(x["so_luong"] - 0.025) < 1e-12 and abs(x["gia_tri_usdt"] - 75) < 1e-9 and abs(x["ky_quy_usdt"] - 25) < 1e-9
       and abs(x["mat_usdt"] - 3.75) < 1e-9 and not x["bo_qua"], str(x))
    # tin nhắn: BTC 75.000, cắt lỗ cách 10% -> tối thiểu 0,001 BTC = 75 USDT, mất 7,5 USDT = 1,97% -> khuyên bỏ qua
    lenh = cc.tao_lenh("BTC", "c", "LONG", {"N": 120, "k": 4.0}, 75000.0, 1875.0, T0 + K * H4)
    t = th.tin_vao(lenh, cfg_thu(c_LONG=True)["loai"]["c_LONG"], T0 + (K + 2) * H4, H4)
    ca("PHẢI CHẶN: rủi ro thật > 1,5% -> tin có chữ KHUYÊN BỎ QUA và số rủi ro thật", "KHUYÊN BỎ QUA" in t and "1,97%" in t, t)
    ca("PHẢI CHẶN: tin không in số lượng dưới tối thiểu", "0,001 BTC" in t and "0,000 BTC" not in t, t)
    lenh = cc.tao_lenh("BTC", "c", "LONG", {"N": 120, "k": 4.0}, 75000.0, 1250.0, T0 + K * H4)   # cắt lỗ 6,7%
    t = th.tin_vao(lenh, cfg_thu(c_LONG=True)["loai"]["c_LONG"], T0 + (K + 2) * H4, H4)
    ca("PHẢI BÁO: rủi ro thật 1-1,5% -> không khuyên bỏ, ghi rõ rủi ro thật hơn 1%",
       "KHUYÊN BỎ QUA" not in t and "1,32%" in t and "hơn 1%" in t, t)
    lenh = cc.tao_lenh("ETH", "c", "LONG", {"N": 120, "k": 4.0}, 3000.0, 37.5, T0 + K * H4)
    t = th.tin_vao(lenh, cfg_thu(c_LONG=True)["loai"]["c_LONG"], T0 + (K + 2) * H4, H4)
    ca("PHẢI BÁO: tin vào ghi số coin, USDT giá trị, ký quỹ x3, USDT mất", "0,025 ETH" in t and "75,0 USDT" in t
       and "ký quỹ 25,0 USDT" in t and "mất 3,75 USDT" in t and "KHUYÊN BỎ QUA" not in t, t)
    # lệnh đã khuyên bỏ qua: không nhắn dời cắt lỗ, tin đóng ghi rõ lệnh ảo
    st = lenh_mo(cat_lo=85.0)
    st["lenhMo"]["BTC|LONG"]["khuyen_bo"] = True
    tong_doi = 0
    for so in (4, 10):
        n4, n1 = nen({"BTC": nen_tang(so)})
        tins, st = th.danh_gia(n4, n1, st, cfg_thu(c_LONG=True), T0 + (K + so + 1) * H4 + 60_000)
        tong_doi += len(loai_tin(tins, "doi_cat_lo"))
    ca("PHẢI CHẶN: lệnh đã khuyên bỏ qua -> không nhắn dời cắt lỗ (vẫn dời nội bộ)",
       tong_doi == 0 and st["lenhMo"]["BTC|LONG"]["cat_lo"] > 85.0)


# ---------------------------------------------------------------- 8. lượt đầu
def ca_luot_dau():
    n4, n1 = nen({c: h4_rows("pha_len", 1) for c in cc.COINS})
    cfg = cfg_thu(c_LONG=True)
    tins, moi = th.danh_gia(n4, n1, {}, cfg, dong_K())
    ca("PHẢI CHẶN: state rỗng, 5 coin đang có tín hiệu -> không mở lệnh hồi tố",
       [t["loai"] for t in tins] == ["bat_dau"] and not moi["lenhMo"])
    ca("PHẢI BÁO: tin bắt đầu liệt kê loại bật/tắt", "Đang BẬT" in tins[0]["text"] and "Đã TẮT" in tins[0]["text"])
    tins, _ = th.danh_gia(n4, n1, moi, cfg, dong_K() + 15 * 60_000)
    ca("PHẢI CHẶN: lượt kế, nến tín hiệu cũ đã đánh dấu -> vẫn không vào", not tins)


# ---------------------------------------------------------------- 9. gửi trượt -> hoàn tác
def ca_hoan_tac():
    n4, n1 = nen({"ETH": h4_rows("pha_len", 1)})
    cfg = cfg_thu(c_LONG=True)
    tins, moi = th.danh_gia(n4, n1, ST, cfg, dong_K())
    for t in reversed(tins):
        th.hoan_tac(moi, t["hoan_tac"])
    ca("PHẢI CHẶN: tin vào gửi trượt -> state không giữ lệnh", "ETH|LONG" not in moi["lenhMo"])
    tins2, _ = th.danh_gia(n4, n1, moi, cfg, dong_K() + 15 * 60_000)
    ca("PHẢI BÁO: lượt sau báo lại tín hiệu đã trượt", len(loai_tin(tins2, "vao", "ETH")) == 1)
    tins, moi = th.danh_gia(n4, n1, {}, cfg, dong_K())
    th.hoan_tac(moi, tins[0]["hoan_tac"])
    ca("PHẢI CHẶN: tin bắt đầu gửi trượt -> state về rỗng (lượt sau gửi lại)", moi == {})
    r = h4_rows("pha_len") + [(T0 + (K + 1) * H4, 105.0, 105.5, 90.0, 92.0)]
    n4, n1 = nen({"BTC": r})
    st = lenh_mo()
    tins, moi = th.danh_gia(n4, n1, st, cfg, T0 + (K + 2) * H4 + 60_000)
    for t in reversed(tins):
        th.hoan_tac(moi, t["hoan_tac"])
    ca("PHẢI CHẶN: tin đóng gửi trượt -> lệnh trở lại, lịch sử không ghi", "BTC|LONG" in moi["lenhMo"] and not moi["lichSu"])


# ---------------------------------------------------------------- 10. định dạng, độ dài, hạn hiệu lực
def ca_dinh_dang():
    ca("PHẢI BÁO: 59.976 USD", cc.gia_vn(59976.4) == "59.976 USD", cc.gia_vn(59976.4))
    ca("PHẢI BÁO: 1,9%", cc.pct_vn(0.019) == "1,9%", cc.pct_vn(0.019))
    ca("PHẢI BÁO: giá XRP có phần lẻ", cc.gia_vn(2.34567) == "2,346 USD", cc.gia_vn(2.34567))
    n4, n1 = nen({c: h4_rows("pha_len", 1) for c in cc.COINS})
    tins, _ = th.danh_gia(n4, n1, ST, cfg_thu(c_LONG=True), dong_K())
    ok = tins and all(len(t["text"]) <= 2000 and "Không phải lời khuyên đầu tư." in t["text"] and "hiệu lực tới" in t["text"]
                      and "Cắt lỗ:" in t["text"] and "2023-2026" in t["text"] for t in tins)
    ca("PHẢI BÁO: tin vào ≤ 2000 ký tự, đủ vùng vào, hạn, cắt lỗ, cỡ lệnh, thống kê, câu miễn trừ", ok)
    tins, moi = th.danh_gia(n4, n1, ST, cfg_thu(c_LONG=True), T0 + (K + 3) * H4)
    ca("PHẢI CHẶN: máy chạy trễ 2 nến -> không vớt tín hiệu của nến cũ", not tins)
    n4, n1 = nen({c: h4_rows("pha_len", 0) for c in cc.COINS})     # nguồn nến chậm: chưa có nến sau nến tín hiệu
    tins, moi = th.danh_gia(n4, n1, ST, cfg_thu(c_LONG=True), T0 + (K + 2) * H4 + 60_000)
    ca("PHẢI CHẶN: nến tín hiệu đóng đã quá hạn hiệu lực -> không gửi, ghi bỏ lỡ", not tins and len(moi["boLo"]) == 5)
    r = h4_rows("pha_len") + [(T0 + (K + 1) * H4, 105.0, 112.0, 104.5, 111.0)]
    n4, n1 = nen({"ETH": r})
    tins, _ = th.danh_gia(n4, n1, ST, cfg_thu(c_LONG=True), T0 + (K + 1) * H4 + 3 * cc.GIO)
    ca("PHẢI CHẶN: giá hiện tại đã chạy khỏi vùng vào -> không gửi", not tins)


# ---------------------------------------------------------------- 11. chống nhìn trước trong hàm dùng chung
def ca_chong_nhin_truoc():
    h = [float(x) for x in range(1, 11)]
    cao, thap = cc.kenh_truoc(h, h, 3)
    ca("PHẢI CHẶN: kênh Donchian không gồm chính nến tín hiệu", cao[5] == 5.0 and thap[5] == 3.0, f"{cao[5]} {thap[5]}")
    t0 = T0 - 300 * D
    rows = [(t0 + d * D, 100 - 0.01 * d, 101, 99, 100 - 0.01 * d) for d in range(249)]
    rows.append((t0 + 249 * D, 98.0, 310.0, 97.0, 300.0))        # ngày cuối vọt lên, chưa đóng ở mốc soát
    ng = cc.dung_ngay(rows)
    ca("PHẢI CHẶN: giữa ngày chưa đóng, bộ lọc ngày chỉ dùng nến ngày đã đóng", cc.phia_ngay(ng, t0 + 249 * D + 12 * cc.GIO) == -1)
    ca("PHẢI BÁO: hết ngày đó thì bộ lọc mới đổi phía", cc.phia_ngay(ng, t0 + 250 * D) == 1)
    thu_hai = cc.dau_tuan(T0) + 7 * D
    rows = [(thu_hai - 210 * D + d * D, 0, 0, 0, 100 + 0.5 * d) for d in range(210)]
    rows += [(thu_hai + d * D, 0, 0, 0, 50.0 - d) for d in range(3)]      # thứ Hai-Tư tuần mới sập mạnh
    rows = [(t, c, c, c, c) for t, _, _, _, c in rows]
    ng = cc.dung_ngay(rows)
    ca("PHẢI CHẶN: RSI tuần không dùng tuần chưa khép", ng["rsi_tuan"][-1] is not None and ng["rsi_tuan"][-1] > 90,
       str(ng["rsi_tuan"][-1]))
    # tính chất chung: chỉ báo tại i KHÔNG đổi khi bỏ hết dữ liệu sau i (không nhìn trước)
    r4, r1 = gia_ngau_nhien(6 * 700, 11)
    full_ng = cc.dung_ngay(r1)
    full = cc.dung_4h(r4, full_ng, full_ng)
    cc._kenh(full, 20)
    lech = []
    for i in range(400, len(r4), 37):
        t_dong = r4[i][0] + H4
        d1 = [x for x in r1 if x[0] + D <= t_dong]
        ng = cc.dung_ngay(d1)
        cut = cc.dung_4h(r4[:i + 1], ng, ng)
        cc._kenh(cut, 20)
        j = len(d1) - 1
        for ten, a1, b1 in (("loc", full["loc"][i], cut["loc"][i]), ("atr", full["atr"][i], cut["atr"][i]),
                            ("rsi", full["rsi"][i], cut["rsi"][i]), ("kenh", full["kenh"][20][0][i], cut["kenh"][20][0][i]),
                            ("rsi_tuan", full_ng["rsi_tuan"][j], ng["rsi_tuan"][j]),
                            ("ema200", full_ng["ema200"][j], ng["ema200"][j])):
            if (a1 is None) != (b1 is None) or (a1 is not None and abs(a1 - b1) > 1e-9 * max(1, abs(a1))):
                lech.append(f"{ten}@{i}")
    ca("PHẢI CHẶN: bỏ dữ liệu sau nến i thì mọi chỉ báo tại i giữ nguyên", not lech, ", ".join(lech[:6]))


# ---------------------------------------------------------------- 12. khớp với máy kiểm thử (dữ liệu giả)
def gia_ngau_nhien(so4, seed):
    rd = random.Random(seed)
    rows, gia = [], 100.0
    for i in range(so4):
        o = gia
        c = max(1.0, o * (1 + rd.gauss(0.0004, 0.02)))
        h = max(o, c) * (1 + abs(rd.gauss(0, 0.006)))
        l = min(o, c) * (1 - abs(rd.gauss(0, 0.006)))
        rows.append((T0 - so4 * H4 + i * H4, o, h, l, c))
        gia = c
    ngay = []
    for i in range(0, so4 - so4 % 6, 6):
        g = rows[i:i + 6]
        ngay.append((g[0][0], g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4]))
    return rows, ngay


def ca_khop_kiem_thu():
    """Tín hiệu danh_gia (cửa sổ 400 nến 4h + 1000 nến ngày) phải trùng tín hiệu tính trên toàn lịch sử."""
    so4 = 6 * 1500
    r4, r1 = gia_ngau_nhien(so4, 7)
    full_ngay = cc.dung_ngay(r1)
    full = cc.dung_4h(r4, full_ngay, full_ngay)
    lech = trung = co_tin = 0
    for p, ho, huong in (({"N": 120, "k": 4.0}, "c", "LONG"), ({"N": 120, "k": 4.0}, "c", "SHORT"),
                         ({"N": 20, "k": 2.0}, "a", "LONG"), ({"N": 20, "k": 2.0}, "a", "SHORT")):
        for i in range(so4 - 1, so4 - 1 - 1200, -1):
            t_dong = r4[i][0] + H4
            w4 = [x for x in r4[max(0, i - th.SO_NEN_4H + 1):i + 1]]
            d1 = [x for x in r1 if x[0] + D <= t_dong][-th.SO_NEN_1D:]
            ng = cc.dung_ngay(d1)
            ctx = cc.dung_4h(w4, ng, ng)
            a = cc.tin_hieu_4h(ctx, len(w4) - 1, ho, huong, p)
            b = cc.tin_hieu_4h(full, i, ho, huong, p)
            co_tin += a or b
            lech += a != b
            trung += a == b
            if i < so4 - 300 and ho == "a":
                break
    ca(f"PHẢI BÁO: tín hiệu máy thật trùng máy kiểm thử ({trung} điểm, {co_tin} có tín hiệu)", lech == 0 and co_tin >= 5,
       f"lệch {lech}")


# ---------------------------------------------------------------- phát lại trên nến thật (tuỳ chọn)
def phat_lai_that(thu_muc, so_ngay=240):
    import kiem_thu_coin as kt
    du, _ = kt.nap(thu_muc, in_ra=lambda *a: None)
    cfg = th.rd(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "coin-backtest.json"), None)
    bat = [(k, m) for k, m in cfg["loai"].items() if m["bat"]]
    t_cuoi = min(du[c]["r4"][-1][0] for c in cc.COINS)
    t_dau = t_cuoi - so_ngay * D
    st = {"batDau": 1, "nenDaXet": {}, "lenhMo": {}, "baoDoiCatLo": {}, "lichSu": [], "boLo": []}
    for c in cc.COINS:
        st["nenDaXet"][f"{c}|4h"] = t_dau - H4
        st["nenDaXet"][f"{c}|1d"] = t_dau - D
    moc = list(range(t_dau, t_cuoi, H4))
    for t in moc:
        bg = t + H4 + 60_000                          # 1 phút sau khi nến 4h mở lúc t đóng
        n4, n1 = {}, {}
        for c in cc.COINS:
            r4 = [x for x in du[c]["r4"] if x[0] <= t + H4][-th.SO_NEN_4H - 1:]
            if r4 and r4[-1][0] == t + H4:            # nến kế tiếp vừa mở: giá hiện tại = giá mở
                x = r4[-1]
                r4[-1] = (x[0], x[1], x[1], x[1], x[1])
            n4[c] = r4
            n1[c] = [x for x in du[c]["r1"] if x[0] + D <= bg][-th.SO_NEN_1D:]
        _, st = th.danh_gia(n4, n1, st, cfg, bg)
    that = sorted((x["coin"], x["huong"], x["tVao"]) for x in st["lichSu"])
    mo = sorted((k.split("|")[0], k.split("|")[1], v["t_tin_hieu"] + H4) for k, v in st["lenhMo"].items())
    kt_ds = []
    for k, m in bat:
        if m["ho"] == "d":
            continue
        for c in cc.COINS:
            for x in kt.mo_phong_4h(c, du[c]["c4"], m["ho"], m["huong"], m["thamSo"], t_dau, kt.VO_CUC):
                kt_ds.append((c, m["huong"], x["t_vao"], x["ly_do"]))
    kt_dong = sorted((a, b, c) for a, b, c, d in kt_ds if d != "het_doan")
    kt_mo = sorted((a, b, c) for a, b, c, d in kt_ds if d == "het_doan")
    ca(f"PHẢI BÁO: phát lại {so_ngay} ngày nến thật: {len(that)} lệnh đã đóng trùng máy kiểm thử",
       that == kt_dong, f"máy thật {len(that)} / kiểm thử {len(kt_dong)}; lệch {set(that) ^ set(kt_dong)}")
    ca(f"PHẢI BÁO: lệnh còn mở trùng ({len(mo)})", mo == kt_mo, f"{mo} vs {kt_mo}")
    print(f"  bỏ lỡ do giá chạy khỏi vùng/quá hạn: {len(st['boLo'])}")


# ---------------------------------------------------------------- 14. chốt tay của Huy + tin không chữ kỹ thuật
CHU_KY_THUAT = ("EMA", "ATR", " R ", " R.", " R,", "Donchian", "Chandelier", "hệ số")


def ca_chot_tay():
    n4, n1 = nen({c: h4_rows("pha_len", 1) for c in cc.COINS})
    cfg = th.ap_chot(cfg_thu(c_LONG=True), {"c_LONG": {"bat": False, "lyDo": "chờ mày chốt"}})
    tins, moi = th.danh_gia(n4, n1, ST, cfg, dong_K())
    ca("PHẢI CHẶN: loại bị chốt tay TẮT -> 5 coin cùng phá đỉnh vẫn không một tin, không lệnh ảo",
       not tins and not moi["lenhMo"], str([t["text"] for t in tins]))
    cfg2 = th.ap_chot(cfg_thu(), {"c_LONG": {"bat": True}})
    tins, _ = th.danh_gia(n4, n1, ST, cfg2, dong_K())
    ca("PHẢI CHẶN: chốt tay không BẬT được loại kiểm thử đã tắt", not tins and cfg2["loai"]["c_LONG"]["bat"] is False)
    tins, _ = th.danh_gia(n4, n1, ST, th.ap_chot(cfg_thu(c_LONG=True), {"c_LONG": {"bat": "false"}}), dong_K())
    ca("PHẢI BÁO: chốt tay ghi sai kiểu (chuỗi) -> không đổi gì, loại vẫn bật", len(loai_tin(tins, "vao")) == 5)
    t = th.tin_bat_dau(cfg)
    ca("PHẢI BÁO: tin bắt đầu in lý do tắt do Huy chốt", "chờ mày chốt" in t, t)


def ca_khong_chu_ky_thuat():
    n4, n1 = nen({c: h4_rows("pha_len", 1) for c in cc.COINS})
    cfg = cfg_thu(c_LONG=True)
    st = copy.deepcopy(ST)
    tong = [th.tin_bat_dau(cfg)]
    tins, st = th.danh_gia(n4, n1, st, cfg, dong_K())
    tong += [x["text"] for x in tins]
    for key, lenh in st["lenhMo"].items():
        tong.append(th.tin_dong(lenh, "cat_lo", lenh["cat_lo"], -1.0, 1.0, lenh["cat_lo"]))
        tong.append(th.tin_doi(lenh, lenh["cat_lo"] * 0.98, 0.5))
    lot = [(w, x[:60]) for x in tong for w in CHU_KY_THUAT if w in x]
    ca("PHẢI CHẶN: tin gửi Huy không chứa chữ kỹ thuật (EMA, ATR, đơn vị R, hệ số...)", len(tong) >= 7 and not lot, str(lot[:3]))


def main(argv):
    for nhom in (ca_khong_vao_trung, ca_nen_chua_dong, ca_loc_short, ca_loai_tat, ca_cat_lo_mot_lan, ca_co_lenh,
                 ca_doi_cat_lo, ca_lenh_san, ca_luot_dau, ca_hoan_tac, ca_dinh_dang, ca_chong_nhin_truoc, ca_khop_kiem_thu,
                 ca_chot_tay, ca_khong_chu_ky_thuat):
        try:
            nhom()
        except Exception as e:     # nhóm ca văng lỗi = TRƯỢT có tiếng, các nhóm khác vẫn chạy
            ca(f"{nhom.__name__} chạy không văng lỗi", False, f"{type(e).__name__}: {e}")
    if "--day-du" in argv:
        thu_muc = os.environ.get("COIN_DU_LIEU", "/Users/Huy/Claude/TinHieuCoin/du-lieu")
        if os.path.isdir(thu_muc):
            phat_lai_that(thu_muc)
        else:
            print(f"Bỏ qua phát lại nến thật: không có {thu_muc}")
    dat = sum(ok for _, ok in CA)
    print(f"{dat}/{len(CA)} ca đạt")
    return 0 if dat == len(CA) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
