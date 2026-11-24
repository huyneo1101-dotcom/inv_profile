#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phần dùng chung của hệ tín hiệu coin (BTC, ETH, SOL, BNB, XRP).

kiem_thu_coin.py (kiểm thử lịch sử) và tin_hieu_coin.py (máy chạy thật) CÙNG gọi các
hàm luật và hàm quản lý lệnh ở đây, nên tín hiệu lúc chạy thật đi đúng luật đã kiểm thử.
Chỉ dùng thư viện chuẩn của Python: máy GitHub Actions không phải cài thêm gì.

Gồm:
  - tải nến: Binance mirror (data-api.binance.vision) trước, trượt thì lùi sang OKX;
  - chỉ báo: EMA, RSI Wilder, ATR Wilder, kênh Donchian của N nến TRƯỚC, RSI tuần;
  - luật vào lệnh của 04 họ (a, b, c, d) và cách quản lý lệnh (cắt lỗ, cắt lỗ đuổi, mục tiêu, hết hạn);
  - cỡ lệnh theo rủi ro 1% vốn, lãi/lỗ theo R sau chi phí;
  - định dạng số kiểu Việt (59.976 USD, 1,9%).
"""
from __future__ import annotations

import bisect
import collections
import csv
import datetime
import json
import math
import os
import time
import urllib.parse
import urllib.request

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
COIN_GOM = ["ETH", "SOL", "BNB", "XRP"]      # vùng mua gom chỉ cho altcoin; BTC đã có bao_zalo.py (MVRV)

GIO = 3600 * 1000
NGAY = 24 * GIO
DO_DAI = {"4h": 4 * GIO, "1d": NGAY}

# Chi phí và rủi ro (Huy chốt 24/11/2026)
PHI = 0.0005            # phí sàn mỗi chiều, tính trên giá trị vị thế
TRUOT = 0.0005          # trượt giá mỗi chiều
QUA_DEM_NGAY = 0.0003   # phí qua đêm hợp đồng tương lai mỗi ngày nắm giữ
RUI_RO = 0.01           # mỗi lệnh dính cắt lỗ mất tối đa 1% tổng vốn = 1R
TRAN_TUONG_LAI = 3.0    # giá trị vị thế tối đa 3 lần vốn
TRAN_MUA_DUT = 1.0      # mua đứt không vay, tối đa 1 lần vốn

# Thông số cố định của từng họ (không nằm trong lưới chọn)
HAN_NEN_B = 30          # họ b: quá 30 nến 4h (5 ngày) chưa chạm cắt lỗ/mục tiêu thì đóng ở giá đóng
HAN_NGAY_D = 180        # họ d: giữ 180 ngày rồi đóng
K_ATR_D = 3.0           # họ d: cắt lỗ 3 lần ATR ngày dưới giá đóng nến tín hiệu
VUNG_VAO_ATR = 0.25     # vùng giá vào = giá tham chiếu ± 0,25 ATR
DOI_TOI_THIEU = 0.005   # cắt lỗ đuổi chỉ dời khi mức mới tốt hơn ≥ 0,5% giá tham chiếu

# Vốn thật và quy cách sàn
# Vốn tính bằng USDT lấy từ biến môi trường VON_USDT (secret GitHub cùng tên). KHÔNG ghi số vào mã:
# kho này công khai. Thiếu biến thì bằng 0 và máy chạy thật dừng có tiếng (tin_hieu_coin.main).
try:
    VON_USDT = float(os.environ.get("VON_USDT") or 0)
except ValueError:
    VON_USDT = 0.0
DON_BAY_KY_QUY = 3      # ký quỹ cô lập đặt đòn bẩy x3 trên sàn
TRAN_RUI_RO_THAT = 0.015  # số lượng tối thiểu của sàn đẩy rủi ro thật vượt 1,5% vốn thì khuyên BỎ QUA
# Binance hợp đồng tương lai USDT-M, đo 24/11/2026 (fapi exchangeInfo): (bước số lượng, giá trị lệnh tối thiểu USDT)
BUOC_SAN = {"BTC": (0.001, 50.0), "ETH": (0.001, 20.0), "SOL": (0.01, 5.0), "BNB": (0.01, 5.0), "XRP": (0.1, 5.0)}

TEN_HO = {
    "a": "Phá vỡ kênh Donchian 4h, lọc EMA200 ngày, cắt lỗ đuổi Chandelier",
    "b": "Vào lúc điều chỉnh (RSI 4h) thuận xu hướng EMA200 ngày, mục tiêu cố định",
    "c": "Như họ a, thêm điều kiện BTC cùng phía EMA200 ngày",
    "d": "Mua gom (mua đứt) khi giá dưới EMA200 ngày sâu và RSI tuần thấp, giữ 180 ngày",
}

BINANCE = "https://data-api.binance.vision/api/v3/klines"
OKX_GAN = "https://www.okx.com/api/v5/market/candles"
OKX_CU = "https://www.okx.com/api/v5/market/history-candles"
BAR_OKX = {"4h": "4H", "1d": "1Dutc"}


# ---------------------------------------------------------------- tải nến
def _lay_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "tin-hieu-coin", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _thu_lai(ham, lan=3, cho=2.0):
    loi = None
    for k in range(lan):
        try:
            return ham()
        except Exception as e:  # mạng chập chờn: thử lại rồi mới coi là trượt
            loi = e
            time.sleep(cho * (k + 1))
    raise loi


def nen_binance(coin, khung, bat_dau=None, ket_thuc=None, so=1000):
    q = {"symbol": coin + "USDT", "interval": khung, "limit": so}
    if bat_dau is not None:
        q["startTime"] = int(bat_dau)
    if ket_thuc is not None:
        q["endTime"] = int(ket_thuc)
    arr = _thu_lai(lambda: _lay_json(BINANCE + "?" + urllib.parse.urlencode(q)))
    if not isinstance(arr, list):
        raise RuntimeError(f"Binance trả về lạ: {str(arr)[:120]}")
    return [(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4])) for k in arr]


def nen_okx(coin, khung, truoc=None, cu=False, so=300):
    q = {"instId": f"{coin}-USDT", "bar": BAR_OKX[khung], "limit": so}
    if truoc is not None:
        q["after"] = int(truoc)          # OKX: 'after' = lấy các nến CŨ HƠN mốc này
    url = (OKX_CU if cu else OKX_GAN) + "?" + urllib.parse.urlencode(q)
    j = _thu_lai(lambda: _lay_json(url))
    if str(j.get("code")) != "0":
        raise RuntimeError(f"OKX từ chối: {str(j)[:160]}")
    return sorted((int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4])) for k in j.get("data", []))


def _hop_nhat(*dsach):
    gop = {}
    for ds in dsach:
        for r in ds:
            gop[r[0]] = r
    return [gop[t] for t in sorted(gop)]


_BINANCE_HONG = {"loi": None}    # Binance trượt một lần trong lượt chạy thì các coin sau đi thẳng OKX


def tai_gan_day(coin, khung, so_nen, bay_gio_ms=None):
    """Nến gần nhất (kể cả nến đang chạy) cho máy chạy thật. Trả (rows, nguồn).
    Binance mirror trước; trượt hoặc dữ liệu cũ thì lùi sang OKX."""
    bay_gio_ms = bay_gio_ms or int(time.time() * 1000)
    dd = DO_DAI[khung]
    loi_bn = _BINANCE_HONG["loi"]
    if loi_bn is None:
        try:
            rows = nen_binance(coin, khung, so=min(so_nen, 1000))
            if not rows or rows[-1][0] < bay_gio_ms - 2 * dd:
                raise RuntimeError("Binance: nến cũ hoặc rỗng")
            return rows, "binance"
        except Exception as e_bn:
            loi_bn = _BINANCE_HONG["loi"] = e_bn
    rows = nen_okx(coin, khung, so=300)
    while len(rows) < so_nen and rows:
        them = nen_okx(coin, khung, truoc=rows[0][0], cu=True, so=300)
        if not them:
            break
        rows = _hop_nhat(them, rows)
        time.sleep(0.15)
    if not rows or rows[-1][0] < bay_gio_ms - 2 * dd:
        raise RuntimeError(f"Cả Binance ({loi_bn}) lẫn OKX đều không cho nến {coin} {khung}")
    return rows[-so_nen:], "okx"


def doc_dem(duong):
    if not os.path.exists(duong):
        return []
    with open(duong, encoding="utf-8") as f:
        return [(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in csv.reader(f) if r and r[0].isdigit()]


def ghi_dem(duong, rows):
    tam = duong + ".tam"
    with open(tam, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["mo_ms", "mo", "cao", "thap", "dong"])
        w.writerows(rows)
    os.replace(tam, duong)


def tai_toan_bo(coin, khung, thu_muc, bay_gio_ms=None, in_ra=print):
    """Toàn bộ lịch sử NẾN ĐÃ ĐÓNG, có đệm CSV tăng dần. Binance mirror trước, OKX lùi."""
    bay_gio_ms = bay_gio_ms or int(time.time() * 1000)
    dd = DO_DAI[khung]
    os.makedirs(thu_muc, exist_ok=True)
    duong = os.path.join(thu_muc, f"{coin}_{khung}.csv")
    cu = doc_dem(duong)
    moi = []
    nguon = "đệm"
    tu = cu[-1][0] + dd if cu else 0
    try:
        while True:
            lo = nen_binance(coin, khung, bat_dau=tu, so=1000)
            moi += lo
            if len(lo) < 1000 or lo[-1][0] + dd >= bay_gio_ms:
                break
            tu = lo[-1][0] + dd
            time.sleep(0.1)
        nguon = "binance"
    except Exception as e:
        in_ra(f"  {coin} {khung}: Binance trượt ({e}) -> lùi sang OKX")
        moi = []
        truoc = None
        moc = cu[-1][0] if cu else 0
        while True:
            lo = nen_okx(coin, khung, truoc=truoc, cu=truoc is not None, so=300)
            if not lo:
                break
            moi = _hop_nhat(lo, moi)
            if lo[0][0] <= moc:
                break
            truoc = lo[0][0]
            time.sleep(0.12)
        nguon = "okx"
    rows = [r for r in _hop_nhat(cu, moi) if r[0] + dd <= bay_gio_ms]   # chỉ giữ nến ĐÃ ĐÓNG
    ghi_dem(duong, rows)
    return rows, nguon


# ---------------------------------------------------------------- chỉ báo
def ema(v, n):
    out = [None] * len(v)
    if len(v) < n:
        return out
    e = sum(v[:n]) / n
    out[n - 1] = e
    k = 2 / (n + 1)
    for i in range(n, len(v)):
        e = v[i] * k + e * (1 - k)
        out[i] = e
    return out


def rsi(c, n=14):
    out = [None] * len(c)
    if len(c) <= n:
        return out
    ag = al = 0.0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]
        ag += max(d, 0)
        al += max(-d, 0)
    ag /= n
    al /= n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def atr(h, l, c, n=14):
    out = [None] * len(c)
    if len(c) < n:
        return out
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    a = sum(tr[:n]) / n
    out[n - 1] = a
    for i in range(n, len(c)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


def kenh_truoc(h, l, n):
    """Cao nhất / thấp nhất của n nến TRƯỚC nến i (không gồm nến i) — chống nhìn trước."""
    cao = [None] * len(h)
    thap = [None] * len(l)
    dq_c, dq_t = collections.deque(), collections.deque()
    for i in range(len(h)):
        if i >= n:
            while dq_c[0] < i - n:
                dq_c.popleft()
            while dq_t[0] < i - n:
                dq_t.popleft()
            cao[i] = h[dq_c[0]]
            thap[i] = l[dq_t[0]]
        while dq_c and h[dq_c[-1]] <= h[i]:
            dq_c.pop()
        dq_c.append(i)
        while dq_t and l[dq_t[-1]] >= l[i]:
            dq_t.pop()
        dq_t.append(i)
    return cao, thap


def dau_tuan(t):
    """Mốc 00:00 UTC thứ Hai của tuần chứa t (1970-01-05 là thứ Hai)."""
    return t - ((t - 4 * NGAY) % (7 * NGAY))


# ---------------------------------------------------------------- bối cảnh khung ngày / 4h
def dung_ngay(rows):
    """Bối cảnh khung ngày từ các nến ngày ĐÃ ĐÓNG."""
    t = [r[0] for r in rows]
    o = [r[1] for r in rows]
    h = [r[2] for r in rows]
    l = [r[3] for r in rows]
    c = [r[4] for r in rows]
    ctx = {"t": t, "t_dong": [x + NGAY for x in t], "o": o, "h": h, "l": l, "c": c,
           "ema200": ema(c, 200), "atr": atr(h, l, c, 14)}
    # RSI tuần: chỉ dùng tuần ĐÃ KHÉP (đủ tới 24:00 Chủ Nhật), giá đóng tuần = giá đóng ngày cuối tuần
    cuoi = (t[-1] + NGAY) if t else 0
    tuan_t, tuan_c = [], []
    for i in range(len(t)):
        ws = dau_tuan(t[i])
        if ws + 7 * NGAY > cuoi:
            break
        if tuan_t and tuan_t[-1] == ws + 7 * NGAY:
            tuan_c[-1] = c[i]
        else:
            tuan_t.append(ws + 7 * NGAY)
            tuan_c.append(c[i])
    r_tuan = rsi(tuan_c, 14)
    ctx["rsi_tuan"] = []
    for i in range(len(t)):
        k = bisect.bisect_right(tuan_t, ctx["t_dong"][i]) - 1
        ctx["rsi_tuan"].append(r_tuan[k] if k >= 0 else None)
    return ctx


def phia_ngay(ngay, t_dong):
    """+1 nếu giá đóng ngày gần nhất ĐÃ ĐÓNG trước mốc t_dong nằm trên EMA200 ngày, -1 nếu dưới, 0 nếu chưa đủ dữ liệu."""
    if ngay is None:
        return 0
    j = bisect.bisect_right(ngay["t_dong"], t_dong) - 1
    if j < 0 or ngay["ema200"][j] is None:
        return 0
    return 1 if ngay["c"][j] > ngay["ema200"][j] else -1


def dung_4h(rows, ngay, ngay_btc=None):
    t = [r[0] for r in rows]
    o = [r[1] for r in rows]
    h = [r[2] for r in rows]
    l = [r[3] for r in rows]
    c = [r[4] for r in rows]
    ctx = {"t": t, "o": o, "h": h, "l": l, "c": c, "atr": atr(h, l, c, 14), "rsi": rsi(c, 14), "kenh": {}}
    dd = DO_DAI["4h"]
    ctx["loc"] = [phia_ngay(ngay, x + dd) for x in t]
    nb = ngay_btc if ngay_btc is not None else ngay
    ctx["loc_btc"] = ctx["loc"] if nb is ngay else [phia_ngay(nb, x + dd) for x in t]
    return ctx


def _kenh(ctx, n):
    if n not in ctx["kenh"]:
        ctx["kenh"][n] = kenh_truoc(ctx["h"], ctx["l"], n)
    return ctx["kenh"][n]


# ---------------------------------------------------------------- luật vào lệnh
def dau(huong):
    return 1 if huong == "LONG" else -1


def tin_hieu_4h(ctx, i, ho, huong, p):
    """True nếu nến 4h thứ i (BẮT BUỘC đã đóng, bên gọi tự bảo đảm) phát tín hiệu vào lệnh."""
    s = dau(huong)
    if ctx["atr"][i] is None or ctx["loc"][i] != s:
        return False
    if ho == "c" and ctx["loc_btc"][i] != s:
        return False
    if ho in ("a", "c"):
        cao, thap = _kenh(ctx, p["N"])
        if cao[i] is None:
            return False
        return ctx["c"][i] > cao[i] if s > 0 else ctx["c"][i] < thap[i]
    if ho == "b":
        r = ctx["rsi"][i]
        if r is None:
            return False
        return r < p["L"] if s > 0 else r > 100 - p["L"]
    return False


def tin_hieu_gom(ngay, j, p):
    """Họ d: nến ngày thứ j (đã đóng) nằm dưới EMA200 ngày hơn X và RSI tuần dưới Y."""
    e, r, a = ngay["ema200"][j], ngay["rsi_tuan"][j], ngay["atr"][j]
    if e is None or r is None or a is None:
        return False
    return ngay["c"][j] < e * (1 - p["X"]) and r < p["Y"]


def tao_lenh(coin, ho, huong, p, gia_tc, atr_tc, t_tin_hieu):
    """Lệnh ảo dựng từ giá đóng nến tín hiệu (giá tham chiếu) và ATR của nến đó."""
    s = dau(huong) if huong != "GOM" else 1
    if ho == "d":
        k = K_ATR_D
    else:
        k = p["k"]
    cat_lo = gia_tc - s * k * atr_tc
    lenh = {"coin": coin, "ho": ho, "huong": huong, "tham_so": dict(p), "t_tin_hieu": int(t_tin_hieu),
            "gia_tc": gia_tc, "atr_tc": atr_tc, "cat_lo": cat_lo, "cat_lo_0": cat_lo, "cuc_tri": gia_tc,
            "so_nen": 0, "muc_tieu": None, "han_nen": None}
    if ho == "b":
        lenh["muc_tieu"] = gia_tc + s * p["T"] * k * atr_tc
        lenh["han_nen"] = HAN_NEN_B
    if ho == "d":
        lenh["han_nen"] = HAN_NGAY_D
    return lenh


def soat_nen(lenh, o, h, l):
    """Soát một nến (đã đóng hoặc đang chạy) với lệnh đang mở. Trả (lý_do, giá_ra_thô) hoặc None.
    Cắt lỗ soát TRƯỚC mục tiêu: nến chạm cả hai tính là dính cắt lỗ."""
    s = 1 if lenh["huong"] in ("LONG", "GOM") else -1
    cl, mt = lenh["cat_lo"], lenh.get("muc_tieu")
    if s > 0:
        if o <= cl:
            return "cat_lo", o
        if l <= cl:
            return "cat_lo", cl
        if mt is not None:
            if o >= mt:
                return "muc_tieu", o
            if h >= mt:
                return "muc_tieu", mt
    else:
        if o >= cl:
            return "cat_lo", o
        if h >= cl:
            return "cat_lo", cl
        if mt is not None:
            if o <= mt:
                return "muc_tieu", o
            if l <= mt:
                return "muc_tieu", mt
    return None


def la_moc_doi(t_mo):
    """True nếu nến 4h mở lúc t_mo đóng đúng 00:00 UTC (07:00 giờ VN): mốc duy nhất trong ngày được dời cắt lỗ."""
    return (t_mo + DO_DAI["4h"]) % NGAY == 0


def sau_nen_dong(lenh, t_mo, h, l, atr_nen):
    """Gọi sau khi một nến ĐÃ ĐÓNG mà lệnh chưa ra. Trả True nếu hết hạn giữ.
    Cắt lỗ đuổi (họ a, c), luật Huy chốt 24/11/2026 vòng sửa 2:
      - đỉnh (Long) / đáy (Short) kể từ lúc vào cập nhật MỌI nến;
      - cắt lỗ CHỈ dời ở nến 4h đóng lúc 00:00 UTC (07:00 VN), mức mới = đỉnh − k×ATR của chính nến đó
        (Short: đáy + k×ATR), và chỉ dời khi tốt hơn mức cũ ≥ 0,5% giá tham chiếu; dời ít hơn thì giữ nguyên.
    Nhờ vậy cắt lỗ của bot = cắt lỗ đã nhắn Huy = cắt lỗ đặt trên sàn, mỗi ngày đổi tối đa một lần."""
    lenh["so_nen"] += 1
    if lenh["ho"] in ("a", "c"):
        k = lenh["tham_so"]["k"]
        if lenh["huong"] == "LONG":
            lenh["cuc_tri"] = max(lenh["cuc_tri"], h)
        else:
            lenh["cuc_tri"] = min(lenh["cuc_tri"], l)
        if la_moc_doi(t_mo) and atr_nen is not None:
            nguong = DOI_TOI_THIEU * lenh["gia_tc"]
            if lenh["huong"] == "LONG":
                moi = lenh["cuc_tri"] - k * atr_nen
                if moi - lenh["cat_lo"] >= nguong:
                    lenh["cat_lo"] = moi
            else:
                moi = lenh["cuc_tri"] + k * atr_nen
                if lenh["cat_lo"] - moi >= nguong:
                    lenh["cat_lo"] = moi
    return lenh["han_nen"] is not None and lenh["so_nen"] >= lenh["han_nen"]


# ---------------------------------------------------------------- cỡ lệnh và R
def co_lenh(gia_vao, cat_lo, mua_dut=False):
    """Giá trị vị thế để dính cắt lỗ mất đúng 1% vốn, chặn trần 3 lần vốn (mua đứt: 1 lần)."""
    kc = abs(gia_vao - cat_lo) / gia_vao
    tran = TRAN_MUA_DUT if mua_dut else TRAN_TUONG_LAI
    dn = min(RUI_RO / kc, tran) if kc > 0 else 0.0
    return {"kc": kc, "gia_tri": dn, "don_bay": dn, "rui_ro": dn * kc, "cham_tran": RUI_RO / kc > tran if kc > 0 else True}


def _so_buoc(x, buoc, len_tren=False):
    """Số bước (nguyên) của x theo bước sàn; mặc định làm tròn XUỐNG. Cộng lề nhỏ chống sai số dấu phẩy động."""
    n = x / buoc
    return int(math.ceil(n - 1e-9)) if len_tren else int(math.floor(n + 1e-9))


def lenh_san(coin, gia_vao, cat_lo, mua_dut=False, von=None):
    """Quy cỡ lệnh 1% rủi ro ra số coin đặt được trên sàn.
    Số lượng làm tròn XUỐNG theo bước sàn (rủi ro không vượt 1%). Nếu số đó dưới tối thiểu của sàn thì nâng lên
    mức tối thiểu và tính rủi ro thật; rủi ro thật > 1,5% vốn thì đánh dấu khuyên BỎ QUA."""
    von = VON_USDT if von is None else von
    buoc, toi_thieu = BUOC_SAN[coin]
    co = co_lenh(gia_vao, cat_lo, mua_dut)
    muc_tieu_usdt = co["gia_tri"] * von
    n = _so_buoc(muc_tieu_usdt / gia_vao, buoc)
    n_min = max(1, _so_buoc(toi_thieu / gia_vao, buoc, len_tren=True))
    nang = n < n_min
    if nang:
        n = n_min
    le = max(0, -int(math.floor(math.log10(buoc) + 1e-9)))
    so_luong = round(n * buoc, le)
    gia_tri = so_luong * gia_vao
    mat = so_luong * abs(gia_vao - cat_lo)
    rui_ro_that = mat / von
    tran = (TRAN_MUA_DUT if mua_dut else TRAN_TUONG_LAI) * von
    bo_qua = rui_ro_that > TRAN_RUI_RO_THAT or gia_tri > tran + 1e-9
    return {"so_luong": so_luong, "le": le, "gia_tri_usdt": gia_tri, "ky_quy_usdt": gia_tri / DON_BAY_KY_QUY,
            "mat_usdt": mat, "phi_usdt": gia_tri * 2 * (PHI + TRUOT), "rui_ro_that": rui_ro_that,
            "nang_len_toi_thieu": nang, "bo_qua": bo_qua, "toi_thieu_usdt": toi_thieu, "buoc": buoc,
            "ti_le_so_voi_ly_thuyet": gia_tri / muc_tieu_usdt if muc_tieu_usdt > 0 else 0.0}


def tinh_R(huong, vao_tho, ra_tho, cat_lo_0, so_ngay):
    """Lãi/lỗ theo R (1R = 1% vốn) SAU phí, trượt giá và phí qua đêm (hợp đồng tương lai)."""
    mua_dut = huong == "GOM"
    s = 1 if huong in ("LONG", "GOM") else -1
    vao = vao_tho * (1 + s * TRUOT)
    ra = ra_tho * (1 - s * TRUOT)
    cl = co_lenh(vao, cat_lo_0, mua_dut)
    loi = s * (ra - vao) / vao - 2 * PHI - (0 if mua_dut else QUA_DEM_NGAY * so_ngay)
    return cl["gia_tri"] * loi / RUI_RO


# ---------------------------------------------------------------- định dạng kiểu Việt
def so_vn(x, le=0):
    s = f"{abs(x):,.{le}f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return ("-" if x < 0 else "") + s


def gia_vn(x):
    a = abs(x)
    le = 0 if a >= 1000 else 1 if a >= 100 else 2 if a >= 10 else 3 if a >= 1 else 4
    return so_vn(x, le) + " USD"


def pct_vn(x, le=1, dau_cong=False):
    """x là tỉ lệ (0,019 -> '1,9%')."""
    s = so_vn(x * 100, le) + "%"
    return ("+" + s) if dau_cong and x > 0 else s


def r_vn(x):
    return ("+" if x > 0 else "") + so_vn(x, 2) + " R"


def gio_vn(ms):
    d = datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc) + datetime.timedelta(hours=7)
    return d.strftime("%H:%M %d/%m")


def ngay_iso(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime("%Y-%m-%d")
