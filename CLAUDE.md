# BTC Tín Hiệu (repo `inv_profile`) — bảng tín hiệu thận trọng cho Bitcoin

> ⚠️ Tên repo `inv_profile` là tên cũ. Nội dung thực tế là **app tín hiệu BTC**, KHÔNG phải profile/portfolio.

App tĩnh một-file: toàn bộ UI + logic + CSS trong `index.html` (~42KB, ~600 dòng), React 18 + Babel Standalone qua CDN, KHÔNG build step. PWA (`manifest.webmanifest` + `sw.js`). Deploy tự động lên GitHub Pages (Actions) khi push `main`. **Trợ lý ra quyết định mua từ từ — không phải lời khuyên đầu tư.**

## Quy tắc làm việc với file này
- `index.html` nhỏ vừa (~600 dòng) nên đọc được cả file, nhưng vẫn nên grep định vị khi sửa nhanh.
- Babel transpile **trong trình duyệt**: lỗi cú pháp = trắng màn hình, KHÔNG báo ở terminal. Luôn kiểm tra Console sau khi sửa (xem skill `smoke-test` / `pwa-healthcheck`).
- Sửa nội dung đáng kể → **bump `C` trong `sw.js`** (hiện: `btc-tin-hieu-v2`), nếu không máy người dùng phục vụ bản cache cũ.

## Thư viện (đã pin version — qua **unpkg.com**, khác họ app kia dùng jsdelivr)
- `react@18.2.0` + `react-dom@18.2.0` (production UMD)
- `@babel/standalone@7.24.7`
- KHÔNG có Supabase, KHÔNG backend. Toàn bộ chạy phía client.

## Dữ liệu (localStorage)
Một khoá duy nhất `btc-tin-hieu:v1` (object JSON), đọc/ghi qua `loadState()` / `saveState()` (dòng ~đầu script). Trường lưu: `etfOutflow`, `mstrSelling`, `etfNote`, `mstrNote`, `notify`, `lastNotifiedDate` (chống nhắc trùng trong ngày). Không có SCHEMA_VERSION — đổi cấu trúc thì xem skill `local-store`.

## Nguồn dữ liệu
- **LIVE phía client (ưu tiên)**: CoinGecko (`market_chart` → giá/EMA50/EMA200/RSI), alternative.me (Sợ hãi & Tham lam), Binance `fapi` (funding). `sw.js` **không cache** 3 API này (luôn lấy mới).
- **Dự phòng/bổ sung — file tĩnh cùng origin `data/*.json`**: `fomc.json` (lịch họp Fed), `btc.json`, `etf.json` (Farside), `mstr.json` (8-K SEC), `onchain.json` (MVRV Z-score), `macro.json` (FRED: DXY/US10Y/M2), `backtest.json`.
- Vì fetch nguồn ngoài nằm ở CI (xem dưới) hoặc là API public CORS-mở, app client hiếm khi dính CORS; nếu API live lỗi thì tự rơi về `data/btc.json`.

## Logic chính (trong `index.html`)
- `computeScore(s)` → **điểm thận trọng tối đa 14** từ nhiều tín hiệu (EMA, FOMC, RSI, F&G, funding, ETF, MSTR, MVRV, macro) → đèn **🟢 ≤3 · 🟡 4–7 · 🔴 ≥8**. Đây là phần "tổng hợp nhanh, CHƯA kiểm chứng".
- `liveRisk()` / `coreTier()` / `pctFromBp()` → nhiệt kế định giá & "regime" (giá vs EMA200) + khung MVRV ~1 năm, **khớp với `backtest.py`** (percentile qua breakpoints). Đây là phần "đã backtest / kiểm chứng OOS".
- Component: một `App` lớn + `Spark` (SVG sparkline) + các helper thuần (`computeEMA`, `computeRSI`, `trendOf`, `daysToNextFOMC`, `fngLabel`).
- Nhắc: `Notification` API — chỉ nhắc khi mở app (app tĩnh không chạy ngầm), 1 lần/ngày khi 🔴 hoặc sát Fed ≤2 ngày.

## Tự cập nhật dữ liệu (GitHub Actions)
- `btc-data.yml` (hằng ngày): giá+EMA+RSI, macro FRED, MVRV, ETF, 8-K MSTR → ghi `data/*.json`.
- `btc-backtest.yml` (hằng tuần): chạy lại `backtest.py` (chống lookahead) → `data/backtest.json`.
- Secret tuỳ chọn `FRED_API_KEY` (Settings → Secrets → Actions). Thiếu key vẫn chạy, chỉ bỏ phần macro.

## Deploy
- **GitHub Pages qua Actions**: Settings → Pages → Source = **GitHub Actions**. Push `main` → live. Có `.nojekyll`.

## Skills dùng chung
Repo hiện CHƯA cài `.claude/skills`. Cài plugin dùng chung: `/plugin marketplace add huyneo1101-dotcom/Claude_skills` → `/plugin install vibe-pwa-kit@huyneo-skills`. Hữu ích ở đây: `smoke-test`, `pwa-healthcheck`, `local-store`, `doc-single-file-app`.
