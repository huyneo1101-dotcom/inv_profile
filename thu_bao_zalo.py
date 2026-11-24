#!/usr/bin/env python3
"""Ca thử cho bao_zalo.tao_tin. Chạy: python3 thu_bao_zalo.py  (mã 0 = đạt)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bao_zalo import tao_tin

BT = {"core": {"regime": {"all": {"bull": {"avgFwd": 30.4, "pctNeg": 33.6},
                                  "bear": {"avgFwd": 8.5, "pctNeg": 51.4}}},
               "longterm": {"current": {"tier": "Thoang", "pct": 12.1}}}}


def bt(tier, pct=50):
    return {"core": {**BT["core"], "longterm": {"current": {"tier": tier, "pct": pct}}}}


def rows(*phia):  # 'b' = trên EMA200, 's' = dưới
    return {"rows": [{"price": 110 if p == "b" else 90, "ema200": 100} for p in phia]}


BTC = {"price": 90, "ema200": 100}
DA = {"zaloStarted": True, "lastRegime": "bear", "lastLongtermTier": "Thoang"}
CA = []


def ca(ten, tin, mong):
    khoa = [k for k, _, _ in tin[0]]
    ok = khoa == mong
    CA.append(ok)
    print(("ĐẠT " if ok else "TRƯỢT ") + ten, khoa)


# PHẢI CHẶN: trạng thái không đổi thì không nhắn lặp
ca("không đổi -> im", tao_tin(BTC, BT, rows("s", "s", "s"), DA), [])
# PHẢI CHẶN: giá vừa vượt EMA200 1-2 ngày chưa được báo LONG
ca("lật 2 ngày -> chưa báo", tao_tin(BTC, BT, rows("s", "b", "b"), DA), [])
ca("lật qua lật lại -> chưa báo", tao_tin(BTC, BT, rows("b", "s", "b"), DA), [])
# PHẢI CHẶN: vào bậc khác Thoang từ bậc không phải Thoang thì không báo
ca("Can chu y -> Rat than trong im", tao_tin(BTC, bt("Rat than trong"), rows("s", "s", "s"),
                                             {**DA, "lastLongtermTier": "Can chu y"}), [])
# PHẢI BÁO
ca("3 ngày trên EMA200 -> LONG", tao_tin(BTC, BT, rows("s", "b", "b", "b"), DA), ["lastRegime"])
ca("3 ngày dưới -> SHORT", tao_tin(BTC, BT, rows("b", "s", "s", "s"), {**DA, "lastRegime": "bull"}), ["lastRegime"])
ca("vào vùng gom -> MUA", tao_tin(BTC, BT, rows("s", "s", "s"), {**DA, "lastLongtermTier": "Can chu y"}), ["lastLongtermTier"])
ca("ra vùng gom -> báo", tao_tin(BTC, bt("Can chu y"), rows("s", "s", "s"), DA), ["lastLongtermTier"])
ca("lần đầu -> tin bắt đầu", tao_tin(BTC, BT, rows("s", "s", "s"), {}), ["zaloStarted"])
t = tao_tin(BTC, BT, rows("b", "s", "s", "s"), {**DA, "lastRegime": "bull"})[0][0][2]
CA.append("XU HƯỚNG DÀI HẠN BTC ĐỔI CHIỀU: GIẢM" in t and "8,5%" in t)
print("ĐẠT" if CA[-1] else "TRƯỢT", "tin đổi chiều GIẢM kèm số lịch sử 90 ngày")
# PHẢI CHẶN: tin xu hướng không được tự xưng là lệnh, không còn câu chê short, phải trỏ sang tin [COIN]
CA.append("KHÔNG ủng hộ short" not in t and "TÍN HIỆU SHORT" not in t and "[COIN]" in t and "không phải lệnh" in t)
print("ĐẠT" if CA[-1] else "TRƯỢT", "tin GIẢM không phải lệnh, trỏ sang hệ [COIN]")
t = tao_tin(BTC, BT, rows("s", "b", "b", "b"), DA)[0][0][2]
CA.append("ĐỔI CHIỀU: TĂNG" in t and "TÍN HIỆU LONG" not in t and "[COIN]" in t and "30,4%" in t)
print("ĐẠT" if CA[-1] else "TRƯỢT", "tin đổi chiều TĂNG không phải lệnh, trỏ sang hệ [COIN]")

print(f"{sum(CA)}/{len(CA)} ca đạt")
sys.exit(0 if all(CA) else 1)
