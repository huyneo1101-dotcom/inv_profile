#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Máy chạy thật: báo tín hiệu coin qua bot Zalo (chạy mỗi 15 phút trên GitHub Actions).

Đọc data/coin-backtest.json (tham số đã chốt + cờ bật/tắt + số đoạn kiểm do kiem_thu_coin.py sinh),
tải nến 4h và nến ngày của BTC, ETH, SOL, BNB, XRP (Binance mirror, trượt thì OKX), rồi:
  - CHỈ xét tín hiệu vào lệnh trên nến ĐÃ ĐÓNG, và chỉ nến đóng gần nhất (không vớt tín hiệu cũ);
  - mỗi lượt soát giá (cả nến đang chạy) với lệnh ảo đang mở để báo chạm cắt lỗ / đóng lệnh;
  - mỗi coin tối đa 01 lệnh mở mỗi chiều (LONG, SHORT, GOM); loại tín hiệu TẮT thì không bao giờ mở lệnh;
  - cắt lỗ đuổi chỉ dời ở nến 4h đóng 00:00 UTC (07:00 VN), nên tin dời đi ngay lượt chạy sau 07:00 VN,
    tối đa 01 tin/coin/ngày; cắt lỗ trong state = cắt lỗ đã nhắn = cắt lỗ đặt trên sàn;
  - cỡ lệnh quy ra USDT theo vốn VON_USDT và bước số lượng của sàn; tối thiểu sàn đẩy rủi ro thật > 1,5% thì khuyên BỎ QUA;
  - lượt đầu (state rỗng) KHÔNG mở lệnh hồi tố, chỉ gửi 01 tin "bắt đầu theo dõi".
State: data/coin-state.json. Gửi trượt thì hoàn tác đúng sự kiện đó (lượt sau báo lại), mã thoát 1.
--thu: in tin ra màn hình, không gửi, không ghi state.

Phần thuần `danh_gia(nen_4h, nen_1d, state, cfg, bay_gio)` tách khỏi mạng và file để ca thử gọi thẳng.
"""
from __future__ import annotations

import bisect
import copy
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coin_chung as cc  # noqa: E402

SO_NEN_4H = 400
SO_NEN_1D = 1000
MAT = "__khong_co__"
THU_TU = ["c_LONG", "a_LONG", "b_LONG", "c_SHORT", "a_SHORT", "b_SHORT", "d_GOM"]
DUOI = "Không phải lời khuyên đầu tư."


# ---------------------------------------------------------------- tên gọi trong tin nhắn
def ten_loai(m):
    """Tên loại tín hiệu bằng lời thường: tin đi tới người không đọc biểu đồ, cấm EMA, ATR, R."""
    ho, huong, p = m["ho"], m["huong"], m.get("thamSo", {})
    if ho in ("a", "c"):
        ngay = p.get("N", 0) * 4 / 24
        so_ngay = cc.so_vn(ngay, 0 if float(ngay).is_integer() else 1)
        if huong == "LONG":
            ten = f"LONG khi giá vượt đỉnh {so_ngay} ngày lúc coin đang trong xu hướng tăng"
        else:
            ten = f"SHORT khi giá thủng đáy {so_ngay} ngày lúc coin đang trong xu hướng giảm"
        return ten + (" và BTC cũng vậy" if ho == "c" else "")
    if ho == "b":
        return f"{huong} lúc giá điều chỉnh ngắn trong xu hướng"
    return "MUA GOM altcoin (mua đứt, giữ 180 ngày)"


def lich_su(m):
    """'2023-2026: 146 lệnh, thắng 42%' từ số đoạn kiểm; không in lãi TB theo R (Huy không dùng đơn vị R)."""
    k = m.get("doanKiem") or {}
    if k.get("n") and k.get("thang") is not None:
        return f"2023-2026: {k['n']} lệnh, thắng {round(k['thang'] * 100)}%"
    return (m.get("dongTin") or "2023-2026: chưa có số").split(", lãi TB")[0]


def ly_do_ngan(m):
    if m.get("lyDoTat"):
        return m["lyDoTat"]
    if m.get("trungVoi"):
        return "gần như trùng với loại đang bật"
    k = m.get("doanKiem") or {}
    if (k.get("n") or 0) < 30:
        return f"thử trên dữ liệu 2023 tới nay chỉ có {k.get('n') or 0} lệnh, quá ít để tin"
    if (k.get("rTB") or 0) < 0:
        return "thử trên dữ liệu 2023 tới nay bị lỗ"
    if (k.get("rTB") or 0) < 0.10 or (k.get("pf") or 0) < 1.2:
        return "thử trên dữ liệu 2023 tới nay lãi quá mỏng"
    return "không qua bài thử trên dữ liệu cũ"


def _hop(text):
    return text if len(text) <= 2000 else text[:1990] + "…"


def _tien(x):
    """Lãi/lỗ USDT bằng lời: 'lãi 4,67 USDT' / 'lỗ 3,80 USDT'."""
    return ("lãi " if x > 0 else "lỗ ") + cc.so_vn(abs(x), 2) + " USDT"


def tin_bat_dau(cfg):
    loai = cfg.get("loai", {})
    bat = [m for k, m in loai.items() if m.get("bat")]
    tat = [m for k, m in loai.items() if not m.get("bat") and not m.get("trungVoi")]
    dong = ["[COIN] Bắt đầu theo dõi BTC, ETH, SOL, BNB, XRP, soát giá mỗi 15 phút.",
            "Đang BẬT:" if bat else "Đang BẬT: chưa loại nào qua bài thử trên dữ liệu cũ, bot sẽ im lặng."]
    for m in bat:
        dong.append(f"- {ten_loai(m)}. Lịch sử {lich_su(m)}.")
    if tat:
        dong.append("Đã TẮT:")
        for m in tat:
            dong.append(f"- {ten_loai(m)}: {ly_do_ngan(m)}.")
    dong.append("Xu hướng tăng hay giảm ở đây là giá nằm trên hay dưới đường trung bình 200 ngày.")
    dong.append("Bot nhắn 03 loại tin: VÀO LỆNH (vùng giá vào, số coin, USDT, ký quỹ, cắt lỗ), DỜI CẮT LỖ "
                "(sau 07:00 sáng, mày sửa lệnh cắt lỗ trên sàn) và ĐÓNG (giá chạm cắt lỗ, sàn tự đóng).")
    dong.append(f"Vốn tính lệnh {cc.so_vn(cc.VON_USDT, 0)} USDT; lệnh nào dính cắt lỗ cũng chỉ mất khoảng 1% vốn. "
                "Thắng ít, lãi dồn vào vài lệnh lớn nên đừng bỏ lệnh. Không mở lệnh hồi tố, chỉ báo tín hiệu từ giờ.")
    dong.append(DUOI)
    return _hop("\n".join(dong))


def tin_vao(lenh, m, han, dd):
    coin, huong = lenh["coin"], lenh["huong"]
    gia, cl, a = lenh["gia_tc"], lenh["cat_lo"], lenh["atr_tc"]
    mua_dut = huong == "GOM"
    co = cc.co_lenh(gia, cl, mua_dut)
    lo, hi = gia - cc.VUNG_VAO_ATR * a, gia + cc.VUNG_VAO_ATR * a
    san = cc.lenh_san(coin, gia, cl, mua_dut)
    sl = cc.so_vn(san["so_luong"], san["le"])
    dau_tin = f"[{coin}] MUA GOM (mua đứt, không đòn bẩy)" if mua_dut else f"[{coin}] VÀO {huong} (hợp đồng tương lai)"
    if san["bo_qua"]:
        dau_tin += ": KHUYÊN BỎ QUA"
    vao = (f"Vào: từ {cc.gia_vn(lo)} đến {cc.gia_vn(hi)}, hiệu lực tới {cc.gio_vn(han)} giờ VN. "
           "Quá giờ hoặc giá đã chạy ra ngoài vùng này thì BỎ QUA.")
    cat_lo = f"Cắt lỗ: {cc.gia_vn(cl)} (cách giá vào {cc.pct_vn(co['kc'])})."
    dong = [dau_tin, f"Loại: {ten_loai(m)}."]
    if san["bo_qua"]:
        dong += [f"KHUYÊN BỎ QUA: lệnh nhỏ nhất sàn cho đặt là {sl} {coin} ≈ {cc.so_vn(san['gia_tri_usdt'], 1)} USDT, "
                 f"dính cắt lỗ mất {cc.so_vn(san['mat_usdt'], 2)} USDT, tức rủi ro thật "
                 f"{cc.pct_vn(san['rui_ro_that'], 2)} vốn, vượt trần 1,5%. Bot vẫn theo dõi lệnh này để giữ số "
                 "thống kê, không nhắn dời cắt lỗ.", vao, cat_lo]
    else:
        dat = f"Đặt: {sl} {coin} ≈ {cc.so_vn(san['gia_tri_usdt'], 1)} USDT"
        if not mua_dut:
            dat += (f", ký quỹ {cc.so_vn(san['ky_quy_usdt'], 1)} USDT (đòn bẩy x{cc.DON_BAY_KY_QUY}, "
                    "ký quỹ cô lập)")
        mat = (f"Dính cắt lỗ mất {cc.so_vn(san['mat_usdt'], 2)} USDT = {cc.pct_vn(san['rui_ro_that'], 2)} vốn "
               f"(cộng phí ~{cc.so_vn(san['phi_usdt'], 2)} USDT).")
        if san["nang_len_toi_thieu"]:
            mat += " Số lượng đã nâng lên mức nhỏ nhất sàn cho đặt nên rủi ro thật hơn 1%."
        if mua_dut:
            chot = (f"Bán: giữ 180 ngày (tới khoảng "
                    f"{cc.gio_vn(lenh['t_tin_hieu'] + dd + cc.HAN_NGAY_D * cc.NGAY)[6:]}), bot báo khi tới hạn "
                    "hoặc khi chạm cắt lỗ.")
        elif lenh["ho"] in ("a", "c"):
            chot = ("Chốt lời: không đặt sẵn. Giá đi đúng hướng thì mỗi sáng sau 07:00 bot nhắn mức cắt lỗ mới để "
                    "mày sửa trên sàn; giá chạm cắt lỗ thì sàn tự đóng lệnh.")
        else:
            chot = (f"Chốt lời: đặt chốt ở {cc.gia_vn(lenh['muc_tieu'])}; quá 5 ngày chưa chạm thì đóng ở giá "
                    "thị trường.")
        dong += [vao, dat + ".", cat_lo + " Đặt lệnh cắt lỗ trên sàn ngay khi khớp.", mat, chot]
    dong.append(f"Lịch sử {lich_su(m)}. Thắng ít, lãi dồn vào vài lệnh lớn nên đừng bỏ lệnh.")
    dong.append(DUOI)
    return _hop("\n".join(dong))


def tin_dong(lenh, ly, gia_ra, R, so_ngay, cl_da_bao):
    """cl_da_bao: cắt lỗ đang nằm trên sàn (đã nhắn Huy) lúc đầu lượt chạy."""
    coin, huong = lenh["coin"], lenh["huong"]
    ten = "MUA GOM" if huong == "GOM" else huong
    ao = lenh.get("khuyen_bo")
    if ly == "het_han":
        cau = (f"hết {cc.HAN_NGAY_D} ngày giữ, BÁN ở giá thị trường (~{cc.gia_vn(gia_ra)})." if huong == "GOM"
               else f"quá 5 ngày chưa chạm mục tiêu, ĐÓNG ở giá thị trường (~{cc.gia_vn(gia_ra)}).")
    elif ly == "muc_tieu":
        cau = f"giá chạm mục tiêu {cc.gia_vn(gia_ra)}, lệnh chốt lời đặt sẵn trên sàn đã tự khớp."
    elif abs(lenh["cat_lo"] - cl_da_bao) > 1e-12 * max(1.0, abs(cl_da_bao)):
        cau = (f"giá chạm cắt lỗ mới {cc.gia_vn(lenh['cat_lo'])} trước khi bot kịp nhắn mức này; trên sàn vẫn là "
               f"cắt lỗ cũ {cc.gia_vn(cl_da_bao)}. ĐÓNG TAY ngay ở giá thị trường.")
    elif abs(gia_ra - lenh["cat_lo"]) > 1e-12 * max(1.0, abs(gia_ra)):
        cau = (f"giá mở nến đã NHẢY QUA cắt lỗ {cc.gia_vn(lenh['cat_lo'])}, ra ở khoảng {cc.gia_vn(gia_ra)}. "
               "Mở sàn kiểm tra: lệnh cắt lỗ thường đã khớp ở giá tệ hơn; chưa khớp thì đóng tay.")
    else:
        cau = f"lệnh cắt lỗ đặt sẵn trên sàn đã tự đóng ở {cc.gia_vn(gia_ra)}. Không cần làm gì."
    ti_le = lenh.get("ti_le_san", 1.0)
    lai = R * cc.RUI_RO * cc.VON_USDT * ti_le
    if ao:
        return _hop(f"[{coin}] Lệnh {ten} đã khuyên bỏ qua vừa đóng, chỉ để giữ số thống kê: "
                    f"{'lãi' if R > 0 else 'lỗ'} {cc.so_vn(abs(R), 2)} lần mức rủi ro 1% vốn, "
                    f"giữ {cc.so_vn(so_ngay, 1)} ngày.")
    return _hop("\n".join([
        f"[{coin}] ĐÓNG {ten}: {cau}",
        f"Kết quả: vào {cc.gia_vn(lenh['gia_tc'])}, ra {cc.gia_vn(gia_ra)}, {_tien(lai)} với số lượng đã báo "
        f"({cc.pct_vn(R * cc.RUI_RO * ti_le, 2, dau_cong=True)} vốn, đã trừ phí ước tính), "
        f"giữ {cc.so_vn(so_ngay, 1)} ngày."]))


def tin_doi(lenh, cu, R_khoa):
    coin, huong = lenh["coin"], lenh["huong"]
    chieu = "lên" if huong in ("LONG", "GOM") else "xuống"
    lai = R_khoa * cc.RUI_RO * cc.VON_USDT * lenh.get("ti_le_san", 1.0)
    return _hop(f"[{coin}] DỜI CẮT LỖ {huong} {chieu} {cc.gia_vn(lenh['cat_lo'])} (đang là {cc.gia_vn(cu)}). "
                "Sửa lệnh cắt lỗ trên sàn sang mức mới; mức này giữ tới 07:00 sáng mai. "
                f"Nếu giá chạm, lệnh đóng với {_tien(lai)}.")


def ap_chot(cfg, chot):
    """Áp quyết định tay của Huy (data/coin-chot.json) lên cấu hình kiểm thử.
    CHỈ được TẮT một loại kiểm thử đang bật, KHÔNG được bật loại kiểm thử đã tắt (an toàn hơn là nhanh)."""
    cfg = copy.deepcopy(cfg)
    for k, v in (chot or {}).items():
        m = (cfg.get("loai") or {}).get(k)
        if not isinstance(m, dict) or not isinstance(v, dict):
            continue
        if v.get("bat") is False and m.get("bat") is True:
            m["bat"] = False
            m["lyDoTat"] = v.get("lyDo") or "mày đã chọn tắt"
    return cfg


# ---------------------------------------------------------------- phần thuần
def _da_dong(rows, khung, bay_gio):
    dd = cc.DO_DAI[khung]
    return [r for r in rows if r[0] + dd <= bay_gio]


def _dang_chay(rows, khung, bay_gio):
    dd = cc.DO_DAI[khung]
    if rows and rows[-1][0] <= bay_gio < rows[-1][0] + dd:
        return rows[-1]
    return None


def _quan_ly(lenh, ctx, dang, dd, bay_gio):
    """Đi qua các nến ĐÃ ĐÓNG sau mốc lệnh đã soát, rồi nến đang chạy. Trả (lý_do, giá_ra, giờ_ra) hoặc None."""
    t = ctx["t"]
    for j in range(bisect.bisect_right(t, lenh["nen_cuoi"]), len(t)):
        kq = cc.soat_nen(lenh, ctx["o"][j], ctx["h"][j], ctx["l"][j])
        if kq:
            return kq[0], kq[1], t[j] + dd
        het = cc.sau_nen_dong(lenh, t[j], ctx["h"][j], ctx["l"][j], ctx["atr"][j])
        lenh["nen_cuoi"] = t[j]
        if het:
            return "het_han", ctx["c"][j], t[j] + dd
    if dang is not None:
        kq = cc.soat_nen(lenh, dang[1], dang[2], dang[3])
        if kq:
            return kq[0], kq[1], bay_gio
    return None


def danh_gia(nen_4h, nen_1d, state, cfg, bay_gio):
    """Hàm thuần. nen_4h/nen_1d: {coin: [(mở_ms, mở, cao, thấp, đóng), ...]} (có thể gồm nến đang chạy).
    Trả (danh_sách_tin, state_mới). Mỗi tin: {loai, coin, text, hoan_tac}; hoan_tac là các thao tác đưa
    state_mới về như cũ cho RIÊNG sự kiện đó nếu gửi trượt."""
    bay_gio = int(bay_gio)
    goc = state or {}
    loai = cfg.get("loai", {}) if isinstance(cfg, dict) else {}
    loai_bat = [(k, loai[k]) for k in THU_TU if k in loai and loai[k].get("bat") is True]
    tins = []

    if not goc.get("batDau"):
        moi = {"phienBan": 1, "batDau": bay_gio, "nenDaXet": {}, "lenhMo": {}, "baoDoiCatLo": {},
               "lichSu": [], "boLo": []}
        for coin in cc.COINS:
            for khung, nen in (("4h", nen_4h), ("1d", nen_1d)):
                dong = _da_dong(nen.get(coin) or [], khung, bay_gio)
                if dong:
                    moi["nenDaXet"][f"{coin}|{khung}"] = dong[-1][0]
        tins.append({"loai": "bat_dau", "coin": None, "text": tin_bat_dau(cfg),
                     "hoan_tac": [("toan_bo", copy.deepcopy(goc))]})
        return tins, moi

    moi = copy.deepcopy(goc)
    for nhom in ("nenDaXet", "lenhMo", "baoDoiCatLo"):
        moi.setdefault(nhom, {})
    moi.setdefault("lichSu", [])
    moi.setdefault("boLo", [])

    d1_btc = _da_dong(nen_1d.get("BTC") or [], "1d", bay_gio)
    ngay_btc = cc.dung_ngay(d1_btc) if d1_btc else None

    for coin in cc.COINS:
        r4, r1 = nen_4h.get(coin) or [], nen_1d.get(coin) or []
        d4, d1 = _da_dong(r4, "4h", bay_gio), _da_dong(r1, "1d", bay_gio)
        dang = {"4h": _dang_chay(r4, "4h", bay_gio), "1d": _dang_chay(r1, "1d", bay_gio)}
        ngay = (ngay_btc if coin == "BTC" else cc.dung_ngay(d1)) if d1 else None
        c4 = cc.dung_4h(d4, ngay, ngay_btc) if d4 else None
        ctx = {"4h": c4, "1d": ngay}

        # 1) quản lý lệnh ảo đang mở (kể cả lệnh của loại vừa bị tắt: Huy đang cầm lệnh thật)
        for huong in ("LONG", "SHORT", "GOM"):
            key = f"{coin}|{huong}"
            lenh = moi["lenhMo"].get(key)
            khung = "1d" if huong == "GOM" else "4h"
            if not lenh or ctx[khung] is None:
                continue
            ban_goc = copy.deepcopy(goc.get("lenhMo", {}).get(key, MAT))
            dd = cc.DO_DAI[khung]
            cl_da_bao = lenh["cat_lo"]          # cắt lỗ đang nằm trên sàn lúc đầu lượt
            ket = _quan_ly(lenh, ctx[khung], dang[khung], dd, bay_gio)
            if ket:
                ly, gia_ra, t_ra = ket
                so_ngay = max(0.0, (t_ra - (lenh["t_tin_hieu"] + dd)) / cc.NGAY)
                R = cc.tinh_R(huong, lenh["gia_tc"], gia_ra, lenh["cat_lo_0"], so_ngay)
                ma = f"{key}|{lenh['t_tin_hieu']}"
                del moi["lenhMo"][key]
                moi["lichSu"] = (moi["lichSu"] + [{"id": ma, "loai": lenh.get("loai"), "coin": coin, "huong": huong,
                                                    "vao": lenh["gia_tc"], "ra": gia_ra, "R": round(R, 3),
                                                    "lyDo": ly, "tVao": lenh["t_tin_hieu"] + dd, "tRa": t_ra}])[-100:]
                tins.append({"loai": "dong", "coin": coin, "khoa": key,
                             "text": tin_dong(lenh, ly, gia_ra, R, so_ngay, cl_da_bao),
                             "hoan_tac": [("dat", "lenhMo", key, ban_goc), ("bo_lich_su", ma)]})
                continue
            if lenh["cat_lo"] != cl_da_bao:
                # chỉ xảy ra sau nến đóng 00:00 UTC; cắt lỗ trong state đổi CÙNG LÚC với tin nhắn (gửi trượt thì hoàn tác)
                hoan = [("dat", "lenhMo", key, ban_goc),
                        ("dat", "baoDoiCatLo", coin, goc.get("baoDoiCatLo", {}).get(coin, MAT))]
                moi["baoDoiCatLo"][coin] = bay_gio
                if lenh.get("khuyen_bo"):
                    continue                     # lệnh ảo đã khuyên bỏ qua: dời im lặng, Huy không cầm lệnh
                so_ngay = (bay_gio - (lenh["t_tin_hieu"] + dd)) / cc.NGAY
                R_khoa = cc.tinh_R(huong, lenh["gia_tc"], lenh["cat_lo"], lenh["cat_lo_0"], so_ngay)
                tins.append({"loai": "doi_cat_lo", "coin": coin, "khoa": key, "text": tin_doi(lenh, cl_da_bao, R_khoa),
                             "hoan_tac": hoan})

        # 2) tín hiệu mới: chỉ nến ĐÃ ĐÓNG gần nhất, mỗi nến xét đúng một lần
        for khung, dong_k in (("4h", d4), ("1d", d1)):
            cx = ctx[khung]
            if not dong_k or cx is None:
                continue
            mk = f"{coin}|{khung}"
            i = len(dong_k) - 1
            t_i = dong_k[i][0]
            if moi["nenDaXet"].get(mk, -1) >= t_i:
                continue
            moc_cu = goc.get("nenDaXet", {}).get(mk, MAT)
            moi["nenDaXet"][mk] = t_i
            dd = cc.DO_DAI[khung]
            for k, m in loai_bat:
                ho, huong, p = m["ho"], m["huong"], m["thamSo"]
                if (ho == "d") != (khung == "1d") or (ho == "d" and coin not in cc.COIN_GOM):
                    continue
                key = f"{coin}|{huong}"
                if key in moi["lenhMo"]:
                    continue   # đã có lệnh mở cùng chiều: không vào trùng
                ok = cc.tin_hieu_gom(cx, i, p) if ho == "d" else cc.tin_hieu_4h(cx, i, ho, huong, p)
                if not ok:
                    continue
                lenh = cc.tao_lenh(coin, ho, huong, p, cx["c"][i], cx["atr"][i], t_i)
                lenh["loai"] = k
                lenh["nen_cuoi"] = t_i
                san = cc.lenh_san(coin, lenh["gia_tc"], lenh["cat_lo"], huong == "GOM")
                lenh["khuyen_bo"] = san["bo_qua"]
                lenh["so_luong"] = san["so_luong"]
                lenh["ti_le_san"] = san["ti_le_so_voi_ly_thuyet"]
                han = t_i + 2 * dd                     # hết nến kế tiếp
                d_k = dang[khung]
                gia_ht = d_k[4] if d_k else cx["c"][i]
                a = cx["atr"][i]
                bo = None
                if bay_gio > han:
                    bo = "quá hạn hiệu lực"
                elif not (lenh["gia_tc"] - cc.VUNG_VAO_ATR * a <= gia_ht <= lenh["gia_tc"] + cc.VUNG_VAO_ATR * a):
                    bo = "giá hiện tại đã ra khỏi vùng vào"
                elif d_k and cc.soat_nen(lenh, d_k[1], d_k[2], d_k[3]):
                    bo = "nến đang chạy đã chạm cắt lỗ"
                if bo:
                    moi["boLo"] = (moi["boLo"] + [{"loai": k, "coin": coin, "t": t_i, "lyDo": bo}])[-50:]
                    continue
                moi["lenhMo"][key] = lenh
                tins.append({"loai": "vao", "coin": coin, "khoa": key, "text": tin_vao(lenh, m, han, dd),
                             "hoan_tac": [("dat", "lenhMo", key, MAT), ("dat", "nenDaXet", mk, moc_cu)]})
    return tins, moi


def hoan_tac(st, ops):
    for op in ops:
        if op[0] == "toan_bo":
            st.clear()
            st.update(copy.deepcopy(op[1]))
        elif op[0] == "dat":
            _, nhom, khoa, gt = op
            d = st.setdefault(nhom, {})
            if gt == MAT:
                d.pop(khoa, None)
            else:
                d[khoa] = copy.deepcopy(gt)
        elif op[0] == "bo_lich_su":
            st["lichSu"] = [x for x in st.get("lichSu", []) if x.get("id") != op[1]]


# ---------------------------------------------------------------- mạng + file
def rd(p, d):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def main(argv):
    thu = "--thu" in argv
    goc = os.environ.get("BTC_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
    p_cfg = os.path.join(goc, "coin-backtest.json")
    p_st = os.path.join(goc, "coin-state.json")
    cfg = rd(p_cfg, None)
    if not cfg or "loai" not in cfg:
        print(f"THIẾU hoặc hỏng {p_cfg}: không biết loại nào bật, dừng (không gửi gì).")
        return 1
    cfg = ap_chot(cfg, rd(os.path.join(goc, "coin-chot.json"), {}))
    if cc.VON_USDT <= 0:
        print("THIẾU biến môi trường VON_USDT (secret GitHub cùng tên): không quy được số coin, dừng (không gửi gì).")
        return 1
    st = rd(p_st, {})
    bay_gio = int(time.time() * 1000)
    nen_4h, nen_1d, loi_tai = {}, {}, []
    for coin in cc.COINS:
        for khung, so, kho in (("4h", SO_NEN_4H, nen_4h), ("1d", SO_NEN_1D, nen_1d)):
            try:
                rows, nguon = cc.tai_gan_day(coin, khung, so, bay_gio)
                kho[coin] = rows
                print(f"{coin} {khung}: {len(rows)} nến từ {nguon}")
            except Exception as e:
                loi_tai.append(f"{coin} {khung}")
                print(f"{coin} {khung}: KHÔNG tải được ({e})")
    if len(loi_tai) == 2 * len(cc.COINS):
        print("Không tải được nến nào: dừng, không ghi state.")
        return 1
    tins, moi = danh_gia(nen_4h, nen_1d, st, cfg, bay_gio)
    if thu:
        for t in tins:
            print(f"--- [{t['loai']}] {len(t['text'])} ký tự\n{t['text']}")
        print(f"Lệnh đang mở sau lượt: {sorted(moi.get('lenhMo', {}))}")
        print("(--thu: không gửi, không ghi state)")
        return 0
    token = os.environ.get("ZALO_BOT_TOKEN", "").strip()
    chat = os.environ.get("ZALO_CHAT_ID", "").strip()
    loi = 0
    if tins and not (token and chat):
        print("THIẾU secret ZALO_BOT_TOKEN/ZALO_CHAT_ID: có tin mà không gửi được, hoàn tác mọi sự kiện.")
    from bao_zalo import gui
    truot, khoa_truot = [], set()
    for t in tins:
        try:
            if not (token and chat):
                raise RuntimeError("thiếu secret")
            if t.get("khoa") and t["khoa"] in khoa_truot:
                raise RuntimeError("tin trước cùng lệnh đã trượt, giữ lại để lượt sau báo đúng thứ tự")
            gui(token, chat, t["text"])
            print("Đã gửi:", t["text"].splitlines()[0])
        except Exception as e:
            print("Gửi trượt:", e, "| hoàn tác:", t["text"].splitlines()[0])
            truot.append(t)
            if t.get("khoa"):
                khoa_truot.add(t["khoa"])
            loi = 1
    for t in reversed(truot):      # hoàn tác ngược thứ tự: tin sau dựng trên kết quả của tin trước
        hoan_tac(moi, t["hoan_tac"])
    if not tins:
        print("Không có tin mới.")
    if moi:
        with open(p_st, "w", encoding="utf-8") as f:
            json.dump(moi, f, ensure_ascii=False, indent=1, sort_keys=True)
    return loi


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
