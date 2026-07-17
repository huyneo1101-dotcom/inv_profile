#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backtest + HIEU CHINH NGUONG cho BTC Tin Hieu (v2).

Khac v1:
- Lich su SAU (nhieu nam) tu CryptoCompare (khong bi chan geo nhu Binance tren runner US;
  CoinGecko free chi cho 365 ngay). Fallback CoinGecko neu loi.
- Them Fear&Greed lich su (alternative.me, tu 2018) vao "core score".
- TU HIEU CHINH nguong den bang walk-forward: chia 70% in-sample de chon nguong,
  30% out-of-sample de KIEM CHUNG (chong overfit). Chi coi la "validated" khi OOS
  van giu thu tu do<vang<xanh ve loi suat tuong lai.

"Core score" (cac tin hieu TINH DUOC TU LICH SU FREE, dung CHUNG voi app):
  - Gia duoi ca EMA50&EMA200: +2 ; nam giua: +1
  - RSI(14) >= 70: +1
  - MVRV Z >= 7: +2 ; >= 5: +1
  - Fear&Greed >= 75 (tham lam tot do): +1
  => range 0..6. App tinh y het core score nay live va map qua nguong da hieu chinh.

CHONG LOOKAHEAD: EMA/RSI tinh bang mang tien tinh (chi dung du lieu <= t). Loi suat
tuong lai chi de CHAM diem, khong dua vao tinh diem.

Chay: python3 backtest.py [--out data/backtest.json] [--horizon 90]
"""
import json, sys, os, datetime, urllib.request

def fetch_json(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "btc-tin-hieu-backtest", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

# ---------- tai lich su ----------
def load_prices():
    """(date, close) tang dan. CryptoCompare histoday (tu ~2017), fallback CoinGecko 365."""
    try:
        out = {}
        to_ts = None
        for _ in range(4):  # 4 x 2000 ngay = du phu tu 2017
            url = "https://min-api.cryptocompare.com/data/v2/histoday?fsym=BTC&tsym=USD&limit=2000"
            if to_ts:
                url += f"&toTs={to_ts}"
            j = fetch_json(url)
            data = (j.get("Data") or {}).get("Data") or []
            if not data:
                break
            for d in data:
                c = d.get("close")
                if c and c > 0:
                    out[datetime.datetime.utcfromtimestamp(d["time"]).strftime("%Y-%m-%d")] = float(c)
            to_ts = data[0]["time"] - 86400
            if len(data) < 2000:
                break
        res = sorted(out.items())
        if len(res) >= 400:
            print(f"Gia: CryptoCompare, {len(res)} ngay ({res[0][0]} -> {res[-1][0]})")
            return res
    except Exception as e:
        print("CryptoCompare loi:", e)
    # fallback CoinGecko
    try:
        j = fetch_json("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=365&interval=daily")
        dd = {}
        for p in j.get("prices", []):
            if isinstance(p[1], (int, float)):
                dd[datetime.datetime.utcfromtimestamp(p[0] / 1000).strftime("%Y-%m-%d")] = p[1]
        res = sorted(dd.items())
        print(f"Gia: CoinGecko fallback, {len(res)} ngay")
        return res
    except Exception as e:
        print("CoinGecko fallback loi:", e)
    return None

def load_mvrv():
    try:
        j = fetch_json("https://bitcoin-data.com/v1/mvrv-zscore")
    except Exception as e:
        print("MVRV history loi:", e); return {}
    out = {}
    if isinstance(j, list):
        for o in j:
            if not isinstance(o, dict): continue
            date = z = None
            for k, v in o.items():
                lk = k.lower()
                if date is None and ("date" in lk or lk == "d" or "time" in lk):
                    date = str(v)[:10]
                if z is None and ("mvrv" in lk or "zscore" in lk or "z-score" in lk):
                    try: z = float(v)
                    except: pass
            if date and z is not None:
                out[date] = z
    print(f"MVRV: {len(out)} ngay")
    return out

def load_fng():
    try:
        j = fetch_json("https://api.alternative.me/fng/?limit=0&format=json")
    except Exception as e:
        print("Fear&Greed history loi:", e); return {}
    out = {}
    for d in j.get("data", []):
        try:
            ts = int(d["timestamp"])
            out[datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")] = int(d["value"])
        except: pass
    print(f"Fear&Greed: {len(out)} ngay")
    return out

# ---------- chi bao (mang tien tinh, O(n)) ----------
def ema_series(vals, period):
    out = [None] * len(vals)
    if len(vals) < period: return out
    k = 2 / (period + 1)
    e = sum(vals[:period]) / period
    out[period - 1] = e
    for i in range(period, len(vals)):
        e = vals[i] * k + e * (1 - k); out[i] = e
    return out

def rsi_series(vals, period=14):
    out = [None] * len(vals)
    if len(vals) < period + 1: return out
    ag = al = 0.0
    for i in range(1, period + 1):
        d = vals[i] - vals[i - 1]
        if d >= 0: ag += d
        else: al -= d
    ag /= period; al /= period
    out[period] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(period + 1, len(vals)):
        d = vals[i] - vals[i - 1]
        ag = (ag * (period - 1) + max(d, 0)) / period
        al = (al * (period - 1) + max(-d, 0)) / period
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out

def core_score(price, e50, e200, rsi, mvrvz, fng):
    """Core score 0..6 — dung CHUNG voi app (sua o day thi sua o app cho dong bo)."""
    s = 0
    if e50 is not None and e200 is not None:
        if price < e50 and price < e200: s += 2
        elif not (price > e50 and price > e200): s += 1
    if rsi is not None and rsi >= 70: s += 1
    if mvrvz is not None:
        if mvrvz >= 7: s += 2
        elif mvrvz >= 5: s += 1
    if fng is not None and fng >= 75: s += 1
    return s

# ---------- thong ke ----------
def _stat(lst):
    if not lst: return None
    avg = sum(lst) / len(lst)
    neg = sum(1 for x in lst if x < 0) / len(lst)
    return {"n": len(lst), "avgFwd": round(avg * 100, 1), "pctNeg": round(neg * 100, 1)}

def tier_of(score, c1, c2):
    return "Thoang" if score <= c1 else "Rat than trong" if score >= c2 else "Can chu y"

def tiers_stats(rows, c1, c2):
    """rows: list (score, fwd). Tra dict tier -> stat."""
    b = {"Thoang": [], "Can chu y": [], "Rat than trong": []}
    for s, f in rows:
        b[tier_of(s, c1, c2)].append(f)
    return {k: _stat(v) for k, v in b.items()}

def calibrate(rows_in, min_n=30):
    """Chon (c1,c2) tren in-sample: don dieu do<vang<xanh + toi da (xanh_avg - do_avg)."""
    best = None
    for c1 in range(0, 6):
        for c2 in range(c1 + 1, 7):
            st = tiers_stats(rows_in, c1, c2)
            g, y, r = st["Thoang"], st["Can chu y"], st["Rat than trong"]
            if not (g and y and r): continue
            if min(g["n"], y["n"], r["n"]) < min_n: continue
            if not (g["avgFwd"] > y["avgFwd"] > r["avgFwd"]): continue
            spread = g["avgFwd"] - r["avgFwd"]
            if best is None or spread > best[0]:
                best = (spread, c1, c2)
    return (best[1], best[2]) if best else None

def main():
    out_path = "data/backtest.json"; horizon = 90
    a = sys.argv[1:]
    for i, x in enumerate(a):
        if x == "--out" and i + 1 < len(a): out_path = a[i + 1]
        if x == "--horizon" and i + 1 < len(a): horizon = int(a[i + 1])

    prices = load_prices()
    if not prices or len(prices) < 300:
        print("Khong du gia — bo qua."); return 0
    mvrv, fng = load_mvrv(), load_fng()
    dates = [d for d, _ in prices]
    vals = [p for _, p in prices]
    e50, e200, rsi = ema_series(vals, 50), ema_series(vals, 200), rsi_series(vals, 14)

    rows = []  # (idx, date, score, fwd90)
    n = len(vals)
    for t in range(200, n - horizon):
        s = core_score(vals[t], e50[t], e200[t], rsi[t], mvrv.get(dates[t]), fng.get(dates[t]))
        fwd = (vals[t + horizon] - vals[t]) / vals[t]
        rows.append((t, dates[t], s, fwd))
    if len(rows) < 200:
        print("Qua it mau sau khi tru horizon."); return 0

    sf = [(s, f) for _, _, s, f in rows]
    split = int(len(rows) * 0.7)
    in_rows = [(s, f) for _, _, s, f in rows[:split]]
    oos_rows = [(s, f) for _, _, s, f in rows[split:]]

    cal = calibrate(in_rows)
    validated = False
    if cal:
        c1, c2 = cal
        oos = tiers_stats(oos_rows, c1, c2)
        g, r = oos["Thoang"], oos["Rat than trong"]
        validated = bool(g and r and g["avgFwd"] > r["avgFwd"])
    else:
        c1, c2 = 1, 3   # mac dinh neu khong tim duoc nguong don dieu

    def fmt_tiers(st):
        order = ["Thoang", "Can chu y", "Rat than trong"]
        return [{"tier": k, **(st[k] or {"n": 0, "avgFwd": None, "pctNeg": None})} for k in order]

    in_stats = tiers_stats(in_rows, c1, c2)
    oos_stats = tiers_stats(oos_rows, c1, c2)
    all_stats = tiers_stats(sf, c1, c2)

    by_score = []
    for sv in range(0, 7):
        st = _stat([f for s, f in sf if s == sv])
        by_score.append({"score": sv, "n": st["n"] if st else 0,
                         "avgFwd": st["avgFwd"] if st else None, "pctNeg": st["pctNeg"] if st else None})

    ti = n - 1
    cur_score = core_score(vals[ti], e50[ti], e200[ti], rsi[ti], mvrv.get(dates[ti]), fng.get(dates[ti]))
    cur_tier = tier_of(cur_score, c1, c2)
    ref = oos_stats if validated else all_stats
    cs = ref.get(cur_tier)
    if cs:
        stmt = (f"Core score hien tai = {cur_score}/6 -> nhom \"{cur_tier}\". "
                f"{'(kiem chung out-of-sample) ' if validated else '(toan bo lich su) '}"
                f"co {cs['n']} lan tuong tu; sau {horizon} ngay, {cs['pctNeg']}% so lan gia THAP hon "
                f"(trung binh {cs['avgFwd']}%).")
    else:
        stmt = f"Core score hien tai = {cur_score}/6, chua du mau nhom \"{cur_tier}\"."

    res = {
        "generatedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": ("Backtest core score (EMA/RSI/MVRV/Fear&Greed) + tu hieu chinh nguong bang "
                 "walk-forward (70% in-sample chon nguong, 30% out-of-sample kiem chung). "
                 "Loi suat = % thay doi gia sau horizon ngay. Khong gom ETF/Fed/funding/macro."),
        "coverage": {"from": dates[200], "to": dates[-1], "days": n, "horizonDays": horizon,
                     "hasMVRV": len(mvrv) > 0, "hasFNG": len(fng) > 0,
                     "trainDays": split, "testDays": len(rows) - split},
        "core": {
            "cutoffs": {"green_max": c1, "red_min": c2},
            "validated": validated,
            "inSample": fmt_tiers(in_stats),
            "outSample": fmt_tiers(oos_stats),
            "all": fmt_tiers(all_stats),
            "byScore": by_score,
            "current": {"date": dates[ti], "score": cur_score, "maxScore": 6,
                        "tier": cur_tier, "usingOOS": validated,
                        **({"n": cs["n"], "avgFwd90": cs["avgFwd"], "pctNeg90": cs["pctNeg"]} if cs else {}),
                        "statement": stmt},
        },
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(res, open(out_path, "w"), ensure_ascii=False, indent=2)
    print("Da ghi", out_path)
    print(f"Nguong: xanh<= {c1}, do>= {c2} | validated={validated}")
    print("OOS tiers:", json.dumps(fmt_tiers(oos_stats), ensure_ascii=False))
    print(stmt)
    return 0

if __name__ == "__main__":
    sys.exit(main())
