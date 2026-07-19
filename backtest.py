#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backtest + hieu chinh cho BTC Tin Hieu (v3 — THIET KE LAI LOI).

Bai hoc tu v2: cong don cac tin hieu MAU THUAN (xu huong giam vs euphoria dinh)
khong tao thang rui ro don dieu — score kep 0..2, khong validate duoc.

v3: CHI SO RUI RO DINH GIA (Valuation Risk 0..100) — gop cac thu CUNG do do "nong/dat":
  - MVRV Z-score (cao = dat)
  - Fear&Greed (cao = tham lam)
  - RSI(14) (cao = qua mua)
  - Do gian gia tren EMA200: price/ema200 - 1 (cao = keo xa trung binh)
Moi thanh phan quy ve PHAN VI LICH SU (0..100) roi lay trung binh -> risk 0..100.
Cao = dat/nong (rui ro mua dinh cao); Thap = re/so hai (vung gom).

Regime (bull/bear) = gia vs EMA200 — de RIENG lam boi canh, khong tron vao risk.

CHONG LOOKAHEAD: percentile tinh kieu EXPANDING (chi dung gia tri <= t) khi backtest.
Nguong tu chon 70% in-sample, kiem chung 30% out-of-sample.
App tinh risk LIVE bang bang breakpoint percentile (core.percentiles) do file nay xuat.

Chay: python3 backtest.py [--out data/backtest.json] [--horizon 90]
"""
import json, sys, os, datetime, time, bisect, urllib.request

def fetch_json(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "btc-tin-hieu-backtest", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

# ---------- tai lich su ----------
def load_prices():
    """(date, close) tang dan. Coinbase candles (tu ~2015, free khong key), fallback CoinGecko 365."""
    try:
        out = {}
        end = datetime.datetime.utcnow()
        for _ in range(16):
            start = end - datetime.timedelta(days=300)
            url = ("https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400"
                   f"&start={start.strftime('%Y-%m-%dT%H:%M:%SZ')}&end={end.strftime('%Y-%m-%dT%H:%M:%SZ')}")
            arr = fetch_json(url)
            if not isinstance(arr, list) or not arr:
                break
            for c in arr:
                if isinstance(c, list) and len(c) >= 5 and c[4]:
                    out[datetime.datetime.utcfromtimestamp(c[0]).strftime("%Y-%m-%d")] = float(c[4])
            end = start
            time.sleep(0.35)
        res = sorted(out.items())
        if len(res) >= 400:
            print(f"Gia: Coinbase, {len(res)} ngay ({res[0][0]} -> {res[-1][0]})")
            return res
    except Exception as e:
        print("Coinbase loi:", e)
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
        print("MVRV loi:", e); return {}
    out = {}
    if isinstance(j, list):
        for o in j:
            if not isinstance(o, dict): continue
            date = z = None
            for k, v in o.items():
                lk = k.lower()
                if date is None and ("date" in lk or lk == "d" or "time" in lk): date = str(v)[:10]
                if z is None and ("mvrv" in lk or "zscore" in lk or "z-score" in lk):
                    try: z = float(v)
                    except: pass
            if date and z is not None: out[date] = z
    print(f"MVRV: {len(out)} ngay")
    return out

def load_fng():
    try:
        j = fetch_json("https://api.alternative.me/fng/?limit=0&format=json")
    except Exception as e:
        print("Fear&Greed loi:", e); return {}
    out = {}
    for d in j.get("data", []):
        try: out[datetime.datetime.utcfromtimestamp(int(d["timestamp"])).strftime("%Y-%m-%d")] = int(d["value"])
        except: pass
    print(f"Fear&Greed: {len(out)} ngay")
    return out

# ---------- chi bao ----------
def ema_series(vals, period):
    out = [None] * len(vals)
    if len(vals) < period: return out
    k = 2 / (period + 1); e = sum(vals[:period]) / period; out[period - 1] = e
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

def breakpoints(values, n=101):
    """101 moc percentile (0..100) tu day du lieu — de app map gia tri live -> percentile."""
    s = sorted(values)
    if not s: return None
    m = len(s)
    return [round(s[min(m - 1, int(round(p / 100 * (m - 1))))], 6) for p in range(n)]

def pct_from_bp(v, bp):
    """Map v -> percentile 0..100 dua tren breakpoints (noi suy tuyen tinh)."""
    if bp is None or v is None: return None
    if v <= bp[0]: return 0.0
    if v >= bp[-1]: return 100.0
    for k in range(len(bp) - 1):
        if v < bp[k + 1]:
            span = bp[k + 1] - bp[k]
            return k + ((v - bp[k]) / span if span else 0)
    return 100.0

# ---------- thong ke ----------
def _stat(lst):
    if not lst: return None
    return {"n": len(lst), "avgFwd": round(sum(lst) / len(lst) * 100, 1),
            "pctNeg": round(sum(1 for x in lst if x < 0) / len(lst) * 100, 1)}

def tier_of(risk, c1, c2):
    return "Thoang" if risk <= c1 else "Rat than trong" if risk >= c2 else "Can chu y"

def tiers_stats(rows, c1, c2):
    b = {"Thoang": [], "Can chu y": [], "Rat than trong": []}
    for r, f in rows: b[tier_of(r, c1, c2)].append(f)
    return {k: _stat(v) for k, v in b.items()}

def calibrate(rows_in, cands, min_n=40):
    """Chon (c1,c2) tren in-sample: don dieu Thoang>CanChuY>RatThanTrong ve loi suat, toi da spread."""
    best = None
    for c1 in cands:
        for c2 in cands:
            if c2 <= c1: continue
            st = tiers_stats(rows_in, c1, c2)
            g, y, r = st["Thoang"], st["Can chu y"], st["Rat than trong"]
            if not (g and y and r): continue
            if min(g["n"], y["n"], r["n"]) < min_n: continue
            if not (g["avgFwd"] > y["avgFwd"] > r["avgFwd"]): continue
            spread = g["avgFwd"] - r["avgFwd"]
            if best is None or spread > best[0]: best = (spread, c1, c2)
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
    dates = [d for d, _ in prices]; vals = [p for _, p in prices]
    n = len(vals)
    rsi = rsi_series(vals, 14); e200 = ema_series(vals, 200)

    # thanh phan tho moi ngay
    comps = {"mvrvZ": [None] * n, "fng": [None] * n, "rsi": [None] * n, "ext": [None] * n}
    for t in range(n):
        comps["mvrvZ"][t] = mvrv.get(dates[t])
        comps["fng"][t] = fng.get(dates[t])
        comps["rsi"][t] = rsi[t]
        comps["ext"][t] = (vals[t] / e200[t] - 1) if e200[t] else None

    # breakpoints tu toan bo lich su (de app map live)
    bp = {k: breakpoints([x for x in comps[k] if x is not None]) for k in comps}

    # risk EXPANDING percentile (chong lookahead) cho backtest
    sorted_hist = {k: [] for k in comps}
    risk = [None] * n
    for t in range(n):
        pcts = []
        for k in comps:
            v = comps[k][t]
            if v is None: continue
            arr = sorted_hist[k]
            if len(arr) >= 30:  # can it nhat 30 diem lich su de percentile co nghia
                pos = bisect.bisect_left(arr, v)
                pcts.append(pos / len(arr) * 100)
            bisect.insort(arr, v)
        if pcts:
            risk[t] = sum(pcts) / len(pcts)

    # rows (risk, fwd90) + regime
    rows = []
    for t in range(200, n - horizon):
        if risk[t] is None: continue
        fwd = (vals[t + horizon] - vals[t]) / vals[t]
        regime = "bull" if (e200[t] and vals[t] > e200[t]) else "bear"
        rows.append((t, dates[t], risk[t], fwd, regime))
    if len(rows) < 200:
        print("Qua it mau."); return 0

    rf = [(r, f) for _, _, r, f, _ in rows]
    split = int(len(rows) * 0.7)
    in_rows = [(r, f) for _, _, r, f, _ in rows[:split]]
    oos_rows = [(r, f) for _, _, r, f, _ in rows[split:]]

    cands = list(range(20, 90, 5))
    cal = calibrate(in_rows, cands)
    if cal:
        c1, c2 = cal
        oos = tiers_stats(oos_rows, c1, c2)
        validated = bool(oos["Thoang"] and oos["Rat than trong"]
                         and oos["Thoang"]["avgFwd"] > oos["Rat than trong"]["avgFwd"])
    else:
        c1, c2, validated = 40, 65, False

    order = ["Thoang", "Can chu y", "Rat than trong"]
    def fmt(st): return [{"tier": k, **(st[k] or {"n": 0, "avgFwd": None, "pctNeg": None})} for k in order]
    in_stats, oos_stats, all_stats = tiers_stats(in_rows, c1, c2), tiers_stats(oos_rows, c1, c2), tiers_stats(rf, c1, c2)

    # bang theo decile risk (minh bach)
    by_bucket = []
    for lo in range(0, 100, 10):
        st = _stat([f for r, f in rf if lo <= r < lo + 10])
        by_bucket.append({"range": f"{lo}-{lo+10}", "n": st["n"] if st else 0,
                          "avgFwd": st["avgFwd"] if st else None, "pctNeg": st["pctNeg"] if st else None})

    # regime x tier (boi canh)
    reg_stat = {}
    for rg in ("bull", "bear"):
        lst = [f for _, _, r, f, g in rows if g == rg]
        reg_stat[rg] = _stat(lst)

    # trang thai hien tai (ngay moi nhat) — dung breakpoints (nhu app)
    ti = n - 1
    cur_pcts, cur_comp = [], {}
    for k in comps:
        v = comps[k][ti]
        p = pct_from_bp(v, bp[k]) if v is not None else None
        cur_comp[k] = {"value": round(v, 3) if v is not None else None,
                       "pct": round(p, 1) if p is not None else None}
        if p is not None: cur_pcts.append(p)
    cur_risk = round(sum(cur_pcts) / len(cur_pcts), 1) if cur_pcts else None
    cur_regime = "bull" if (e200[ti] and vals[ti] > e200[ti]) else "bear"
    cur_tier = tier_of(cur_risk, c1, c2) if cur_risk is not None else None
    ref = oos_stats if validated else all_stats
    cs = ref.get(cur_tier) if cur_tier else None
    if cs and cs["n"] > 0:
        stmt = (f"Rui ro dinh gia hien tai = {cur_risk}/100 -> nhom \"{cur_tier}\", regime {cur_regime}. "
                f"{'(out-of-sample) ' if validated else '(toan bo lich su) '}"
                f"co {cs['n']} lan tuong tu; sau {horizon} ngay, {cs['pctNeg']}% so lan gia THAP hon "
                f"(TB {cs['avgFwd']}%).")
    else:
        stmt = f"Rui ro dinh gia = {cur_risk}/100." if cur_risk is not None else "Chua du du lieu."

    res = {
        "generatedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": ("v3: Chi so RUI RO DINH GIA (MVRV+Fear&Greed+RSI+do gian tren EMA200, theo phan vi "
                 "lich su, 0..100). Cao=dat/nong. Nguong tu chon in-sample, kiem chung out-of-sample. "
                 "Regime bull/bear de rieng. App tinh live bang core.percentiles. Qua khu khong dam bao tuong lai."),
        "coverage": {"from": dates[200], "to": dates[-1], "days": n, "horizonDays": horizon,
                     "hasMVRV": len(mvrv) > 0, "hasFNG": len(fng) > 0,
                     "trainDays": split, "testDays": len(rows) - split},
        "core": {
            "model": "valuation-risk-percentile",
            "cutoffs": {"green_max": c1, "red_min": c2},
            "validated": validated,
            "percentiles": bp,
            "components": ["mvrvZ", "fng", "rsi", "ext"],
            "inSample": fmt(in_stats), "outSample": fmt(oos_stats), "all": fmt(all_stats),
            "byBucket": by_bucket,
            "regime": {k: (reg_stat[k] or {"n": 0}) for k in reg_stat},
            "current": {"date": dates[ti], "risk": cur_risk, "tier": cur_tier, "regime": cur_regime,
                        "usingOOS": validated, "components": cur_comp,
                        **({"n": cs["n"], "avgFwd90": cs["avgFwd"], "pctNeg90": cs["pctNeg"]} if cs else {}),
                        "statement": stmt},
        },
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(res, open(out_path, "w"), ensure_ascii=False, indent=2)
    print("Da ghi", out_path)
    print(f"Nguong risk: xanh<= {c1}, do>= {c2} | validated={validated}")
    print("OOS:", json.dumps(fmt(oos_stats), ensure_ascii=False))
    print("Decile:", json.dumps(by_bucket, ensure_ascii=False))
    print(stmt)
    return 0

if __name__ == "__main__":
    sys.exit(main())
