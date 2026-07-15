#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backtest bo luat "diem than trong" cua BTC Tin Hieu.

Y tuong: tua nguoc lich su, moi ngay tinh lai diem theo bo luat (chi cac tin hieu
TINH DUOC TU LICH SU FREE: xu huong EMA, RSI, MVRV Z-score), roi do loi suat 30/90
ngay SAU do de xem den do/vang/xanh co that su ung voi giai doan nen tranh/nen mua.

CHONG LOOKAHEAD: moi ngay t chi dung du lieu <= t. Loi suat tuong lai chi de CHAM diem,
khong dua vao tinh diem.

HAN CHE (noi that): backtest KHONG gom ETF/Fed/funding/Fear&Greed vi thieu lich su free
du dai. Vi vay day la kiem chung PHAN LOI cua bo luat (phan on-chain + ky thuat), du de
biet nen mong co vung chac khong.

Chay: python3 backtest.py [--out data/backtest.json] [--horizon 90]
Khong co mang -> in canh bao va thoat (Action se chay o noi co mang).
"""
import json, sys, os, datetime, urllib.request

# ---------- tai du lieu ----------
def fetch_json(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "btc-tin-hieu-backtest", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def load_prices():
    """Tra ve list (date_str, price) tang dan theo ngay. Thu days=max, fallback 365."""
    for days in ("max", "365"):
        try:
            j = fetch_json(f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days={days}&interval=daily")
            pr = j.get("prices", [])
            out = [(datetime.datetime.utcfromtimestamp(p[0] / 1000).strftime("%Y-%m-%d"), p[1])
                   for p in pr if isinstance(p[1], (int, float))]
            # gop trung ngay (giu ban cuoi)
            dd = {}
            for d, v in out:
                dd[d] = v
            res = sorted(dd.items())
            if len(res) >= 250:
                return res
        except Exception as e:
            print(f"CoinGecko days={days} loi:", e)
    return None

def load_mvrv():
    """dict date_str -> mvrv z. Best-effort, loi thi tra {}."""
    try:
        j = fetch_json("https://bitcoin-data.com/v1/mvrv-zscore")
    except Exception as e:
        print("MVRV history khong lay duoc:", e); return {}
    out = {}
    if isinstance(j, list):
        for o in j:
            if not isinstance(o, dict): continue
            date = None; z = None
            for k, v in o.items():
                lk = k.lower()
                if date is None and ("date" in lk or lk == "d" or "time" in lk):
                    date = str(v)[:10]
                if z is None and ("mvrv" in lk or "zscore" in lk or "z-score" in lk):
                    try: z = float(v)
                    except: pass
            if date and z is not None:
                out[date] = z
    return out

# ---------- chi bao (thuan, test duoc offline) ----------
def ema(vals, period):
    if len(vals) < period: return None
    k = 2 / (period + 1); e = sum(vals[:period]) / period
    for x in vals[period:]: e = x * k + e * (1 - k)
    return e

def rsi(vals, period=14):
    if len(vals) < period + 1: return None
    ag = al = 0.0
    for i in range(1, period + 1):
        d = vals[i] - vals[i - 1]
        if d >= 0: ag += d
        else: al -= d
    ag /= period; al /= period
    for i in range(period + 1, len(vals)):
        d = vals[i] - vals[i - 1]
        ag = (ag * (period - 1) + max(d, 0)) / period
        al = (al * (period - 1) + max(-d, 0)) / period
    if al == 0: return 100.0
    return 100 - 100 / (1 + ag / al)

def subscore(price, e50, e200, r, mvrvz):
    """Bo luat con (lich su): tra (score, tier)."""
    s = 0
    if e50 is not None and e200 is not None:
        if price < e50 and price < e200: s += 2
        elif not (price > e50 and price > e200): s += 1
    if r is not None and r >= 70: s += 1
    if mvrvz is not None:
        if mvrvz >= 7: s += 2
        elif mvrvz >= 5: s += 1
    tier = "Thoang" if s <= 1 else "Can chu y" if s <= 3 else "Rat than trong"
    return s, tier

# ---------- backtest ----------
def run_backtest(prices, mvrv, horizon=90):
    """prices: list (date, price) tang dan. Tra dict ket qua."""
    vals = [p for _, p in prices]
    dates = [d for d, _ in prices]
    n = len(vals)
    buckets = {}   # tier -> list fwd return (horizon)
    buckets30 = {}
    per_day = []   # (date, score, tier) — de lay ngay cuoi
    H2 = 30
    for t in range(200, n):
        window = vals[:t + 1]
        price = vals[t]
        e50, e200, r = ema(window[-260:], 50), ema(window[-260:], 200), rsi(window[-120:], 14)
        # dung EMA200 can >=200 diem -> tinh tren toan window de dung
        e200 = ema(window, 200)
        e50 = ema(window[-200:], 50)
        z = mvrv.get(dates[t])
        s, tier = subscore(price, e50, e200, r, z)
        per_day.append((dates[t], s, tier))
        if t + horizon < n:
            fwd = (vals[t + horizon] - price) / price
            buckets.setdefault(tier, []).append(fwd)
        if t + H2 < n:
            fwd2 = (vals[t + H2] - price) / price
            buckets30.setdefault(tier, []).append(fwd2)

    def stat(lst):
        if not lst: return None
        avg = sum(lst) / len(lst)
        neg = sum(1 for x in lst if x < 0) / len(lst)
        return {"n": len(lst), "avg": round(avg * 100, 1), "pctNeg": round(neg * 100, 1)}

    order = ["Thoang", "Can chu y", "Rat than trong"]
    tiers = []
    for tt in order:
        s90 = stat(buckets.get(tt, []))
        s30 = stat(buckets30.get(tt, []))
        tiers.append({"tier": tt,
                      "n90": s90["n"] if s90 else 0,
                      "avgFwd90": s90["avg"] if s90 else None,
                      "pctNeg90": s90["pctNeg"] if s90 else None,
                      "avgFwd30": s30["avg"] if s30 else None})
    # ngay cuoi cung (trang thai hien tai)
    last_date, last_s, last_tier = per_day[-1]
    cur_stat = stat(buckets.get(last_tier, []))
    current = {"date": last_date, "subscore": last_s, "tier": last_tier,
               "n": cur_stat["n"] if cur_stat else 0,
               "avgFwd90": cur_stat["avg"] if cur_stat else None,
               "pctNeg90": cur_stat["pctNeg"] if cur_stat else None}
    if cur_stat and cur_stat["n"] > 0:
        current["statement"] = (
            f"Trang thai hien tai o nhom \"{last_tier}\". Trong qua khu co {cur_stat['n']} lan tuong tu; "
            f"sau {horizon} ngay, {cur_stat['pctNeg']}% so lan gia THAP hon (trung binh {cur_stat['avg']}%).")
    else:
        current["statement"] = "Chua du du lieu lich su cho nhom nay."
    return {"coverage": {"from": dates[200], "to": dates[-1], "days": n, "horizonDays": horizon,
                         "hasMVRV": len(mvrv) > 0},
            "tiers": tiers, "current": current}

def main():
    out_path = "data/backtest.json"; horizon = 90
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--out" and i + 1 < len(args): out_path = args[i + 1]
        if a == "--horizon" and i + 1 < len(args): horizon = int(args[i + 1])
    prices = load_prices()
    if not prices:
        print("Khong lay duoc gia (co mang khong?). Bo qua — khong ghi de backtest.json."); return 0
    mvrv = load_mvrv()
    res = run_backtest(prices, mvrv, horizon)
    res["generatedAt"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    res["note"] = ("Backtest phan loi bo luat (EMA/RSI/MVRV). Khong gom ETF/Fed/funding/Fear&Greed "
                   "vi thieu lich su free. Loi suat = % thay doi gia sau horizon ngay.")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(res, open(out_path, "w"), ensure_ascii=False, indent=2)
    print("Da ghi", out_path)
    print(json.dumps(res["tiers"], ensure_ascii=False, indent=2))
    print("Hien tai:", res["current"]["statement"])
    return 0

if __name__ == "__main__":
    sys.exit(main())
