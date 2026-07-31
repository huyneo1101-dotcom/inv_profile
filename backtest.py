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

def load_cm_mvrv():
    """MVRV ratio tu Coin Metrics Community API (free, khong key, lich su sau tu ~2010)."""
    out = {}
    try:
        url = ("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
               "?assets=btc&metrics=CapMVRVCur&frequency=1d&page_size=10000")
        j = fetch_json(url)
        for row in j.get("data", []):
            t = row.get("time", "")[:10]
            v = row.get("CapMVRVCur")
            if t and v is not None:
                try: out[t] = float(v)
                except: pass
    except Exception as e:
        print("Coin Metrics MVRV loi:", e)
    print(f"CM MVRV: {len(out)} ngay")
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

def longterm_analysis(dates, vals, cm_mvrv, horizon=365, min_n=40):
    """Khung DAI HAN: dinh gia theo MVRV (percentile lich su) -> loi suat ~1 nam.
    Ky vong: MVRV thap (re) -> loi suat 1 nam CAO; MVRV cao (dat) -> THAP (don dieu giam)."""
    n = len(vals)
    mv = [cm_mvrv.get(d) for d in dates]
    if sum(1 for x in mv if x is not None) < 500:
        return None
    # expanding percentile (chong lookahead) + breakpoints toan bo (cho current)
    hist = []; pct = [None] * n
    for t in range(n):
        v = mv[t]
        if v is not None:
            if len(hist) >= 200:  # can du lich su -> tranh nhieu percentile giai doan dau
                pct[t] = bisect.bisect_left(hist, v) / len(hist) * 100
            bisect.insort(hist, v)
    bp = breakpoints([v for v in mv if v is not None])
    rows = []
    for t in range(200, n - horizon):
        if pct[t] is None: continue
        rows.append((pct[t], (vals[t + horizon] - vals[t]) / vals[t]))
    if len(rows) < 200: return None
    split = int(len(rows) * 0.7)
    in_rows, oos_rows = rows[:split], rows[split:]
    cands = list(range(20, 90, 5))
    cal = calibrate(in_rows, cands, min_n=min_n)
    if cal:
        c1, c2 = cal
        oos = tiers_stats(oos_rows, c1, c2)
        # kiem chung bang TAN SUAT giam (ben hon avgFwd — tranh outlier bull chu ky):
        # dinh gia RE (Thoang) phai it lan giam hon dinh gia DAT (Rat than trong).
        validated = bool(oos["Thoang"] and oos["Rat than trong"]
                         and oos["Thoang"]["n"] >= 40 and oos["Rat than trong"]["n"] >= 40
                         and oos["Thoang"]["pctNeg"] < oos["Rat than trong"]["pctNeg"])
    else:
        c1, c2, validated = 33, 66, False
    order = ["Thoang", "Can chu y", "Rat than trong"]
    def fmt(st): return [{"tier": k, **(st[k] or {"n": 0, "avgFwd": None, "pctNeg": None})} for k in order]
    in_s, oos_s, all_s = tiers_stats(in_rows, c1, c2), tiers_stats(oos_rows, c1, c2), tiers_stats(rows, c1, c2)
    by_bucket = []
    for lo in range(0, 100, 20):
        st = _stat([f for r, f in rows if lo <= r < lo + 20])
        by_bucket.append({"range": f"{lo}-{lo+20}", "n": st["n"] if st else 0,
                          "avgFwd": st["avgFwd"] if st else None, "pctNeg": st["pctNeg"] if st else None})
    # current: ngay moi nhat co MVRV
    ti = max(i for i in range(n) if mv[i] is not None)
    cur_mv = mv[ti]; cur_pct = pct_from_bp(cur_mv, bp)
    cur_tier = tier_of(cur_pct, c1, c2)
    ref = oos_s if validated else all_s
    cs = ref.get(cur_tier)
    if cs and cs["n"] > 0:
        stmt = (f"MVRV hien tai = {round(cur_mv,2)} (phan vi {round(cur_pct)}/100) -> \"{cur_tier}\". "
                f"{'(out-of-sample) ' if validated else '(toan bo lich su) '}"
                f"{cs['n']} lan tuong tu, sau 1 nam TB {cs['avgFwd']}%, {cs['pctNeg']}% so lan giam.")
    else:
        stmt = f"MVRV = {round(cur_mv,2)} (phan vi {round(cur_pct)}/100)."
    return {"horizon": horizon, "model": "mvrv-valuation", "cutoffs": {"green_max": c1, "red_min": c2},
            "validated": validated, "percentiles": bp, "from": dates[ti - len(rows)] if ti - len(rows) >= 0 else dates[200],
            "inSample": fmt(in_s), "outSample": fmt(oos_s), "all": fmt(all_s), "byBucket": by_bucket,
            "current": {"date": dates[ti], "mvrv": round(cur_mv, 3), "pct": round(cur_pct, 1), "tier": cur_tier,
                        "usingOOS": validated,
                        **({"n": cs["n"], "avgFwd": cs["avgFwd"], "pctNeg": cs["pctNeg"]} if cs else {}),
                        "statement": stmt}}

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
    cm_mvrv = load_cm_mvrv()
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

    # ===== TIN HIEU CHINH = REGIME (gia vs EMA200). Backtest 10 nam cho thay day la
    #       tin hieu SACH nhat o khung 90 ngay (bull >> bear). Rui ro dinh gia chi la
    #       nhiet ke boi canh (o khung nay momentum lan at, khong bao giam). =====
    split = int(len(rows) * 0.7)
    def reg_stats(rws):
        b = {"bull": [], "bear": []}
        for _, _, r, f, g in rws: b[g].append(f)
        return {k: _stat(v) for k, v in b.items()}
    reg_in, reg_oos, reg_all = reg_stats(rows[:split]), reg_stats(rows[split:]), reg_stats(rows)
    # Kiem chung bang TAN SUAT giam (pctNeg) — ben hon lay trung binh (it nhay outlier):
    # regime bull phai it lan giam hon bear tren out-of-sample.
    validated = bool(reg_oos["bull"] and reg_oos["bear"]
                     and reg_oos["bull"]["n"] >= 40 and reg_oos["bear"]["n"] >= 40
                     and reg_oos["bull"]["pctNeg"] < reg_oos["bear"]["pctNeg"])

    # nhiet ke rui ro dinh gia — decile (boi canh, minh bach quan he thuc te)
    rf = [(r, f) for _, _, r, f, _ in rows]
    by_bucket = []
    for lo in range(0, 100, 10):
        st = _stat([f for r, f in rf if lo <= r < lo + 10])
        by_bucket.append({"range": f"{lo}-{lo+10}", "n": st["n"] if st else 0,
                          "avgFwd": st["avgFwd"] if st else None, "pctNeg": st["pctNeg"] if st else None})

    # trang thai hien tai
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
    ref = reg_oos if validated else reg_all
    rstat = ref.get(cur_regime)
    b_all, be_all = reg_all.get("bull"), reg_all.get("bear")
    if rstat and rstat["n"] > 0:
        stmt = (f"Regime hien tai = {cur_regime} (gia {'tren' if cur_regime=='bull' else 'duoi'} EMA200). "
                f"{'(out-of-sample) ' if validated else '(toan bo lich su) '}"
                f"sau {horizon} ngay: TB {rstat['avgFwd']}%, {rstat['pctNeg']}% so lan gia THAP hon. "
                f"[Bull vs Bear toan lich su: {b_all['avgFwd'] if b_all else '?'}% vs {be_all['avgFwd'] if be_all else '?'}%]. "
                f"Nhiet ke rui ro dinh gia = {cur_risk}/100 (boi canh).")
    else:
        stmt = f"Regime = {cur_regime}. Rui ro dinh gia = {cur_risk}/100."

    res = {
        "generatedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": ("v3.1: Tin hieu CHINH = REGIME (gia vs EMA200) — backtest 10 nam cho thay day la "
                 "tin hieu sach nhat o khung 90 ngay (bull >> bear). Rui ro dinh gia (MVRV+Fear&Greed+"
                 "RSI+do gian tren EMA200, phan vi lich su 0..100) chi la NHIET KE boi canh: o khung 90 "
                 "ngay momentum lan at nen no KHONG bao giam. Qua khu khong dam bao tuong lai."),
        "coverage": {"from": dates[200], "to": dates[-1], "days": n, "horizonDays": horizon,
                     "hasMVRV": len(mvrv) > 0, "hasFNG": len(fng) > 0,
                     "trainDays": split, "testDays": len(rows) - split},
        "core": {
            "model": "regime-primary",
            "validated": validated,
            "regime": {"inSample": reg_in, "outSample": reg_oos, "all": reg_all},
            "risk": {"percentiles": bp, "byBucket": by_bucket,
                     "components": ["mvrvZ", "fng", "rsi", "ext"]},
            "current": {"date": dates[ti], "regime": cur_regime, "risk": cur_risk,
                        "usingOOS": validated, "components": cur_comp,
                        "regimeStat": rstat or {"n": 0}, "statement": stmt},
            "longterm": longterm_analysis(dates, vals, cm_mvrv, horizon=365),
        },
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(res, open(out_path, "w"), ensure_ascii=False, indent=2)
    print("Da ghi", out_path)
    print(f"Regime validated={validated} | bull={reg_all.get('bull')} bear={reg_all.get('bear')}")
    print("Decile risk:", json.dumps(by_bucket, ensure_ascii=False))
    print(stmt)
    return 0

if __name__ == "__main__":
    sys.exit(main())
