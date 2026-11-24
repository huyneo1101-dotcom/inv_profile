#!/usr/bin/env python3
"""Báo tín hiệu BTC qua bot Zalo (hộ justus_huy, chỉ một mình Huy nhận).

Chạy trong btc-data.yml sau khi data/*.json đã cập nhật. Chỉ báo khi TRẠNG THÁI ĐỔI,
không báo lặp mỗi ngày:
  (i)   NÊN MUA VÀO  — định giá dài hạn (MVRV, backtest.json) chuyển vào bậc "Thoang"
        (phân vị <= 33/100, vùng gom). Ra khỏi vùng cũng báo để dừng tăng mua.
  (ii)  XU HƯỚNG DÀI HẠN BTC ĐỔI CHIỀU — giá vượt lên / thủng xuống EMA200, phải giữ 3 ngày liền
        trong history.json mới tính là đổi pha (chặn báo lật qua lật lại khi giá quanh EMA200).
        Đây là BỐI CẢNH 90 ngày, không phải lệnh: lệnh vào/ra cụ thể do tin [COIN] của hệ tín hiệu
        coin (tin_hieu_coin.py) gửi (sửa 24/11/2026 để hai hệ không nói hai lời ngược nhau).
Lần chạy đầu (state rỗng) gửi một tin "bắt đầu theo dõi" kèm trạng thái hiện tại.

Gửi trượt thì KHÔNG ghi trạng thái của sự kiện đó (mai báo lại) và trả mã 1 cho
workflow đỏ lên. --thu: in tin ra màn hình, không gửi, không ghi state.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

APP_URL = "https://huyneo1101-dotcom.github.io/inv_profile/"
SO_NGAY_XAC_NHAN = 3
API = "https://bot-api.zaloplatforms.com/bot{token}/sendMessage"


def rd(p, d):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def usd(x):
    return f"{x:,.0f}".replace(",", ".") + " USD"


def so(x):
    return f"{x:.1f}".replace(".", ",")


def pha_xac_nhan(rows, n=SO_NGAY_XAC_NHAN):
    """'bull'/'bear' nếu n dòng cuối đều cùng phía EMA200, ngược lại None."""
    tot = [r for r in rows if r.get("price") and r.get("ema200")]
    if len(tot) < n:
        return None
    phia = {"bull" if r["price"] > r["ema200"] else "bear" for r in tot[-n:]}
    return phia.pop() if len(phia) == 1 else None


def thong_ke_pha(bt, pha):
    s = (((bt.get("core") or {}).get("regime") or {}).get("all") or {}).get(pha) or {}
    if s.get("avgFwd") is None:
        return ""
    return (f" Lịch sử 10 năm: sau 90 ngày ở pha này giá TB {'+' if s['avgFwd'] >= 0 else ''}"
            f"{so(s['avgFwd'])}%, {so(s['pctNeg'])}% số lần thấp hơn.")


def tao_tin(btc, bt, hist, st):
    """Trả (danh sách (khoá_state, giá_trị, nội_dung), state_im) — state_im ghi không cần gửi."""
    tin, im = [], {}
    gia = btc.get("price")
    e200 = btc.get("ema200")
    lt = ((bt.get("core") or {}).get("longterm") or {}).get("current") or {}
    bac, pct = lt.get("tier"), lt.get("pct")
    pha = pha_xac_nhan(hist.get("rows", []))
    dong_gia = f"Giá {usd(gia)}" + (f", đường trung bình 200 ngày {usd(e200)}" if e200 else "") + "." if gia else ""

    if not st.get("zaloStarted"):
        ten_pha = {"bull": "pha TĂNG (giá trên đường trung bình 200 ngày)", "bear": "pha GIẢM (giá dưới đường trung bình 200 ngày)"}.get(pha, "chưa rõ pha")
        ten_bac = "VÙNG GOM — nên mua vào dần" if bac == "Thoang" else (f"bậc {bac}" if bac else "chưa có số")
        nd = (f"[BTC] Bắt đầu báo tín hiệu qua Zalo.\nHiện tại: {ten_pha}; định giá dài hạn {ten_bac}"
              + (f" (MVRV phân vị {round(pct)}/100)" if pct is not None else "") + f".\n{dong_gia}\n"
              "Từ giờ chỉ nhắn khi: vào/ra vùng nên mua, hoặc xu hướng dài hạn đổi chiều.\n" + APP_URL)
        tin.append(("zaloStarted", True, nd))
        im["lastRegime"] = pha or st.get("lastRegime")
        im["lastLongtermTier"] = bac or st.get("lastLongtermTier")
        return tin, im

    if bac and bac != st.get("lastLongtermTier"):
        if bac == "Thoang":
            nd = (f"[BTC] NÊN MUA VÀO: định giá dài hạn vào vùng gom (MVRV phân vị "
                  f"{round(pct) if pct is not None else '?'}/100). {dong_gia}\n"
                  "Gợi ý: tăng mua dần (DCA), chia nhiều lệnh, đừng dồn một lần.\n"
                  "Không phải lời khuyên đầu tư.\n" + APP_URL)
            tin.append(("lastLongtermTier", bac, nd))
        elif st.get("lastLongtermTier") == "Thoang":
            nd = (f"[BTC] HẾT VÙNG GIÁ RẺ: định giá dài hạn lên bậc \"{bac}\". {dong_gia}\n"
                  "Gợi ý: dừng tăng mua, về mức mua đều bình thường.\n" + APP_URL)
            tin.append(("lastLongtermTier", bac, nd))
        else:
            im["lastLongtermTier"] = bac

    if pha and pha != st.get("lastRegime"):
        chieu = "TĂNG" if pha == "bull" else "GIẢM"
        phia = "trên" if pha == "bull" else "dưới"
        nd = (f"[BTC] XU HƯỚNG DÀI HẠN BTC ĐỔI CHIỀU: {chieu}, giá nằm {phia} đường trung bình 200 ngày {SO_NGAY_XAC_NHAN} ngày liền. "
              f"{dong_gia}" + thong_ke_pha(bt, pha) + "\n"
              "Đây là bối cảnh cho khoảng 90 ngày tới, không phải lệnh vào. Lệnh vào/ra cụ thể "
              "(giá vào, cắt lỗ, cỡ lệnh) do tin [COIN] của hệ tín hiệu coin gửi.\n" + APP_URL)
        tin.append(("lastRegime", pha, nd))
    return tin, im


def gui(token, chat, text):
    req = urllib.request.Request(
        API.format(token=token),
        data=json.dumps({"chat_id": chat, "text": text[:2000]}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.load(r)
    if not j.get("ok"):
        raise RuntimeError(f"Zalo từ chối: {str(j)[:200]}")


def main(argv):
    thu = "--thu" in argv
    goc = os.environ.get("BTC_DATA_DIR", "data")
    p_st = os.path.join(goc, "push-state.json")
    btc = rd(os.path.join(goc, "btc.json"), {})
    bt = rd(os.path.join(goc, "backtest.json"), {})
    hist = rd(os.path.join(goc, "history.json"), {"rows": []})
    st = rd(p_st, {})
    tin, im = tao_tin(btc, bt, hist, st)
    if thu:
        for _, _, nd in tin:
            print(nd, "\n---")
        print("state_im:", im)
        return 0
    token = os.environ.get("ZALO_BOT_TOKEN", "").strip()
    chat = os.environ.get("ZALO_CHAT_ID", "").strip()
    if tin and not (token and chat):
        print("THIẾU secret ZALO_BOT_TOKEN/ZALO_CHAT_ID — có tin mà không gửi được.")
        return 1
    loi = 0
    st.update({k: v for k, v in im.items() if v is not None})
    for khoa, gt, nd in tin:
        try:
            gui(token, chat, nd)
            print("Đã gửi:", nd.splitlines()[0])
            st[khoa] = gt
            if khoa == "zaloStarted":
                st.update({k: v for k, v in im.items() if v is not None})
        except Exception as e:
            print("Gửi trượt:", e)
            loi = 1
    if not tin:
        print("Không có tín hiệu mới.")
    with open(p_st, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2, sort_keys=True)
    return loi


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
