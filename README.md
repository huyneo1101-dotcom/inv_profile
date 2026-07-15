# BTC Tín Hiệu (inv_profile)

Bảng tín hiệu thận trọng cho Bitcoin — **trợ lý ra quyết định mua từ từ, không phải lời khuyên đầu tư**. App tĩnh một-file (React + Babel CDN, PWA), deploy tự động lên GitHub Pages khi push vào `main`.

## Tín hiệu tổng hợp → đèn 🟢🟡🔴
App tính một "điểm thận trọng" (tối đa 14) từ nhiều nguồn, rồi ra đèn: **≤3 🟢 Thoáng · 4–7 🟡 Cần chú ý · ≥8 🔴 Rất thận trọng**.

| Tín hiệu | Nguồn | Điểm |
|---|---|---|
| Giá dưới EMA50 & EMA200 / giằng co | CoinGecko (live) | +2 / +1 |
| Sát cuộc họp Fed (FOMC) | Lịch có sẵn `data/fomc.json` | +2 (≤3 ngày) / +1 (≤7) |
| RSI(14) > 70 quá mua | tính từ giá | +1 |
| Sợ hãi & Tham lam ≥ 75 | alternative.me | +1 |
| Funding rate cao (long nóng) | Binance | +1 |
| Dòng ETF rút ra | Farside (auto) hoặc tay | +1 |
| MicroStrategy bán lớn | SEC EDGAR (info) + tay | +1 |
| MVRV Z-score ≥ 7 / ≥ 5 | bitcoin-data.com | +2 / +1 |
| 10Y tăng / Đô mạnh / M2 co | FRED | +1 mỗi cái |

Các tín hiệu "cơ hội" (RSI<30, sợ hãi tột độ, funding âm, MVRV vùng đáy, M2 nới) hiển thị dạng ghi chú xanh, không cộng điểm.

## Backtest (kiểm chứng lịch sử)
`backtest.py` tua ngược lịch sử, chấm điểm bộ luật (phần EMA/RSI/MVRV — chống lookahead), đo lợi suất 30/90 ngày sau và gom theo nhóm. App hiển thị câu xác suất dựa trên tiền lệ. Chạy hằng tuần qua Action, hoặc `python3 backtest.py`.

## Dữ liệu tự cập nhật (GitHub Actions)
- **`btc-data.yml`** (hằng ngày): giá+EMA+RSI, macro FRED, MVRV, ETF, 8-K MicroStrategy, append `data/history.json`.
- **`btc-backtest.yml`** (hằng tuần): chạy lại backtest.
- App **ưu tiên lấy LIVE phía client**; các file `data/*.json` là bản dự phòng/bổ sung.

## Thiết lập
1. **Bật GitHub Pages**: Settings → Pages → Source = **GitHub Actions**.
2. **(Tuỳ chọn) Macro FRED**: Settings → Secrets and variables → Actions → thêm secret `FRED_API_KEY` (lấy free tại [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html)). Thiếu key thì app vẫn chạy, chỉ bỏ phần macro.

## ⚠️ Miễn trừ
Đây là công cụ tổng hợp tín hiệu để tham khảo, **không phải lời khuyên đầu tư**. Không tín hiệu nào đảm bảo giá lên hay xuống. Quá khứ không đảm bảo tương lai.
