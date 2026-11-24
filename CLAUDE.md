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
- **Báo Zalo** (bước cuối `btc-data.yml`, script `bao_zalo.py`, ca thử `thu_bao_zalo.py`): nhắn bot JustUs hộ `justus_huy` (chỉ Huy nhận) khi (i) định giá dài hạn vào/ra bậc `Thoang` = NÊN MUA VÀO; (ii) giá ở trên/dưới EMA200 đủ 3 ngày liền = XU HƯỚNG DÀI HẠN BTC ĐỔI CHIỀU (bối cảnh 90 ngày, KHÔNG phải lệnh; lệnh cụ thể do tin [COIN] của hệ tín hiệu coin gửi, sửa 24/11/2026). Chỉ báo khi đổi trạng thái, chống trùng bằng `data/push-state.json`. Secret `ZALO_BOT_TOKEN` + `ZALO_CHAT_ID` (cắm 24/11/2026 từ `congcu/gui_zalo.py`). Gửi trượt ⇒ bước đỏ, state không ghi, hôm sau báo lại.
- Secret tuỳ chọn `FRED_API_KEY` (Settings → Secrets → Actions). Thiếu key vẫn chạy, chỉ bỏ phần macro.

## Tín hiệu giao dịch coin qua Zalo (BTC, ETH, SOL, BNB, XRP), dựng 24/11/2026
Hệ riêng, mượn hàm `gui` của `bao_zalo.py`. Tiền thật: số phải trung thực, cấm nới ngưỡng.
- `coin_chung.py`: tải nến (Binance mirror `data-api.binance.vision` → lùi OKX `candles`/`history-candles`, bar `4H`/`1Dutc`), chỉ báo, luật vào lệnh, quản lý lệnh (cắt lỗ, cắt lỗ đuổi, mục tiêu, hết hạn), cỡ lệnh 1% rủi ro trần x3, số kiểu Việt. Máy kiểm thử và máy thật CÙNG gọi các hàm này.
- `kiem_thu_coin.py`: kiểm thử 4 họ luật × chiều; chọn tham số chỉ trên 2017-08 → 2022-12-31, kiểm 2023-01-01 → nay; ghi `data/coin-backtest.json` (tham số, cờ `bat`, số đoạn kiểm in vào tin). Ngưỡng BẬT: đoạn kiểm ≥ 30 lệnh, hệ số ≥ 1,2, lãi TB ≥ +0,10 R, đoạn dựng luật hệ số ≥ 1,1, tham số kề bên không sụp. `--chi-thong-ke` (chạy hằng tuần trong `btc-backtest.yml`) giữ nguyên tham số, chỉ được TẮT loại tụt ngưỡng, KHÔNG tự BẬT. Đệm nến CSV để ngoài repo (`/Users/Huy/Claude/TinHieuCoin/du-lieu/` trên Mac, thư mục tạm trên máy Actions).
- `tin_hieu_coin.py` (`coin-signal.yml`, mỗi 15 phút): hàm thuần `danh_gia(nen_4h, nen_1d, state, cfg, bay_gio)`; chỉ xét nến đã đóng gần nhất; mỗi coin tối đa 01 lệnh mở mỗi chiều; soát cắt lỗ cả trong nến đang chạy; cắt lỗ đuổi CHỈ dời ở nến 4h đóng 00:00 UTC (07:00 VN), khi tốt hơn ≥ 0,5% giá tham chiếu, nên cắt lỗ trong state = mức đã nhắn = mức đặt trên sàn và chạm cắt lỗ thì sàn tự đóng; cỡ lệnh quy ra USDT theo vốn `VON_USDT` đọc từ secret GitHub cùng tên (KHÔNG ghi số vốn vào kho công khai; đổi secret khi chủ app nạp/rút; thiếu secret thì máy dừng, không gửi) và bước số lượng sàn `BUOC_SAN` (Binance hợp đồng tương lai, đo 24/11/2026), tối thiểu sàn đẩy rủi ro thật > 1,5% vốn thì tin khuyên BỎ QUA; lượt đầu chỉ gửi tin "bắt đầu theo dõi". State `data/coin-state.json` (commit khi đổi). Gửi trượt ⇒ hoàn tác đúng sự kiện, mã 1. `--thu` = in tin, không gửi, không ghi.
- `data/coin-chot.json`: quyết định tay của chủ app, áp lên `coin-backtest.json` ở máy chạy thật (`ap_chot`); CHỈ được tắt loại đang bật, không bật được loại kiểm thử đã tắt. Từ 25/11/2026: `c_SHORT` tắt theo chốt của chủ app (QD-381), bật lại phải qua bảng chọn.
- Tin nhắn viết bằng lời thường cho người không đọc biểu đồ: cấm EMA, ATR, đơn vị R, hệ số (ca `ca_khong_chu_ky_thuat` chặn).
- `thu_tin_hieu_coin.py`: ca thử không gọi mạng (chạy trước máy thật trong workflow); `--day-du` phát lại nến thật đã đệm và so từng lệnh với máy kiểm thử.
- Bật (vòng sửa 2, 24/11/2026): LONG và SHORT phá vỡ đỉnh/đáy 20 ngày (120 nến 4h), lọc EMA200 ngày của coin VÀ của BTC, cắt lỗ đuổi 4 ATR 4h dời mỗi ngày lúc 07:00 VN. Tắt: vào lúc điều chỉnh RSI (lỗ cả hai đoạn), mua gom altcoin (đoạn kiểm 6 lệnh), phá vỡ không lọc BTC (trùng). Số chi tiết và chỗ yếu: `/Users/Huy/Claude/TinHieuCoin/BAO-CAO-KIEM-THU.md`.
- Giao việc dựng hoặc sửa bot giao dịch: hỏi NGAY ĐẦU việc chủ app đặt lệnh thật trên sàn ra sao (sàn nào, lệnh chờ hay khớp ngay, đòn bẩy, có đặt sẵn cắt lỗ trên sàn không) rồi mới viết luật và tin. Vấp 24/11/2026: thiếu ý này nên tin và cắt lỗ phải sửa thêm một vòng (~10 phút trợ lý).
- Đổi luật hoặc lưới ⇒ chạy lại đầy đủ `kiem_thu_coin.py` (KHÔNG cờ), chạy `thu_tin_hieu_coin.py --day-du`, rồi mới đẩy; đổi luật sau khi đã nhìn số đoạn kiểm là làm đoạn kiểm mất giá trị, phải ghi rõ trong commit.

## Deploy
- **GitHub Pages qua Actions**: Settings → Pages → Source = **GitHub Actions**. Push `main` → live. Có `.nojekyll`.

## Skills dùng chung
Repo hiện CHƯA cài `.claude/skills`. Cài plugin dùng chung: `/plugin marketplace add huyneo1101-dotcom/Claude_skills` → `/plugin install vibe-pwa-kit@huyneo-skills`. Hữu ích ở đây: `smoke-test`, `pwa-healthcheck`, `local-store`, `doc-single-file-app`.
