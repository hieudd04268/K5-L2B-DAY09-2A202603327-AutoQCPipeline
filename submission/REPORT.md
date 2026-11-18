# Báo cáo Day 09 — Đinh Đức Hiếu, 2A202603327

## 1. Kết luận trước
Pipeline kết luận **Hold** (mã thoát 10): **0 lỗi bắt buộc** còn lại nhưng **38/202 ảnh (18.8%)**
vẫn còn cảnh báo chưa được người duyệt, vượt ngưỡng 10%.
Vào **224 ảnh**, ra **202 ảnh** (`submission/export/clean_v1/`, bản NHÁP — `manifest.json` ghi `decision: Hold`);
22 ảnh bị loại ở cửa vào (8 trùng byte, 4 trùng gần đúng, 5 rò rỉ test/val, 2 hỏng, 3 quá nhỏ).
Lý do chính: lô có nhiều lỗi ngữ nghĩa hơn sức người duyệt — hàng đợi **125 ảnh** nhưng ngân sách chỉ **80 ảnh** (đã dùng hết 80/80).

## 2. Lỗi và phân việc
Lấy từ `02_error_list_v1` (202 ảnh qua cửa vào + 22 ảnh bị loại ở cửa vào; tổng 224).
**58 lỗi bắt buộc** (22 ở cửa vào + 36 trong nhãn) và **149 cảnh báo trên 114/202 ảnh**.

| Mã lỗi | Số ảnh/dòng | Ai sửa | Vì sao |
|---|---:|---|---|
| `DUP_IMAGE_EXACT` | 8 ảnh | máy (loại ảnh) | trùng từng byte (md5): chắc chắn trùng |
| `DUP_IMAGE_NEAR` | 4 ảnh | máy (loại ảnh) | phash ≤ 10; đã mở xem các cặp, đúng là cùng ảnh |
| `LEAK_TEST` | 5 ảnh | máy (loại ảnh) | trùng ảnh test/val: giữ lại sẽ làm metric đẹp giả |
| `CORRUPT_IMAGE` / `BAD_SIZE` | 2 / 3 ảnh | máy (loại ảnh) | không mở được / cạnh ngắn < 250px |
| `BAD_FORMAT` | 3 dòng | máy (xoá dòng) | thiếu cột / `nan`: không thể đoán lại toạ độ |
| `BAD_CLASS_ID` | 6 dòng | máy (xoá dòng) | id 93, 7, 4, −1 không thuộc lớp nào |
| `BOX_ZERO` | 4 dòng | máy (xoá dòng) | box không có diện tích |
| `DUP_BOX` | 7 dòng | máy (xoá dòng sau) | hai box cùng lớp IoU > 0.9 |
| `BOX_OUT_OF_IMAGE` | 8 dòng | máy (cắt box) | lớp đúng, chỉ tràn mép: cắt về [0,1] |
| `BAD_CLASS_NAME` | 2 (data.yaml) | máy (ghi lại tên lớp) | `Person`, `Bus` sai hoa/thường |
| `MISSING_LABEL_FILE` | 6 ảnh | **người** (gán mới) | máy không được bịa nhãn; file rỗng = "ảnh nền", khác "chưa gán" |
| `POSSIBLE_MISSING` | 53 / 52 ảnh | **người** | model lớn thấy vật mà nhãn không có — có thể model sai |
| `POSSIBLE_LOOSE_BOX` | 28 / 24 ảnh | **người** | box lệch; cần mắt người xem vật thật |
| `POSSIBLE_FALSE_POS` | 25 / 24 ảnh | **người** | box không khớp vật nào model thấy |
| `POSSIBLE_WRONG_CLASS` | 18 / 18 ảnh | **người** | car↔truck↔bus: lỗi ý nghĩa, chỉ người phân xử |
| `EMPTY_LABEL` | 12 ảnh | **người** | ảnh nền thật hay thiếu nhãn? |
| `BOX_TINY` / `BOX_HUGE` | 6 / 3 dòng | **người** | có thể là vật thật ở xa / chiếm cả ảnh |
| `CLASS_RARE` | 4 | — (theo dõi) | id lạ (93, 7, 4, −1) mỗi cái 1 box; hết sau khi xoá dòng |

Máy tự sửa **35 thay đổi** (`03_fixes.csv`: 20 `drop_line`, 8 `clip_box`, 1 `rename_classes`, 6 `needs_label`), mỗi thay đổi ghi trước → sau.
Sau khi sửa (`04_error_list_v2`): còn **6 lỗi bắt buộc** (đúng 6 ảnh thiếu nhãn) và **148 cảnh báo trên 112 ảnh**.

**Hàng đợi** (`05_review_queue.csv`, **125 ảnh**) xếp theo điểm ưu tiên = tổng (trọng số mã × (1 + conf của model)):
`NEEDS_LABEL` = 10 nên 6 ảnh chưa có nhãn lên đầu (hạng 2–7); `WRONG_CLASS` = 3, `MISSING`/`FALSE_POS` = 2 được ưu tiên hơn
`LOOSE_BOX` = 1.5 và `BOX_TINY` = 0.3. Đứng đầu là `img_0020` (11.5 điểm: vừa bị xoá dòng id 93, vừa nghi thiếu nhãn và nhầm lớp).

**Ngân sách 80/125 ảnh**: người duyệt xem được **18/18 ảnh WRONG_CLASS**, **50/52 ảnh MISSING**, nhưng chỉ **12/23 ảnh FALSE_POS** và
**8/24 ảnh LOOSE_BOX** (trọng số thấp nên nằm cuối hàng). 45 ảnh không ai xem → **38/202 ảnh còn cảnh báo** → Hold.

## 3. Calibration (2 ngưỡng)
Sweep trên `data/calib/` (39 ảnh, đáp án `MANIFEST.csv`) — `submission/calibration/calibration_report.md`; sau đó chạy thử từng giá trị trên raw.

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **10** | `DUP_IMAGE_NEAR` 1.00 / 0.50 → **1.00 / 0.67**; `DUP_IMAGE_EXACT` 1.00 / 1.00 (giữ nguyên) | Cờ = **xoá hẳn ảnh** nên ưu tiên **precision**: chọn mức nhỏ nhất tăng recall mà precision vẫn 1.00. Trên raw chỉ loại thêm 3 ảnh (19 → 22/224); đã mở xem cả 3 cặp mới, đều trùng thật (`img_0186` ~ `img_0061` đổi độ sáng, `img_0223` ~ `img_0077` cắt + thu nhỏ). Mức 12–14 không bắt thêm cặp nào. |
| `second_opinion.conf` | 0.25 | **0.6** | `MISSING` 0.50 / 1.00 → **0.57 / 1.00**; `WRONG_CLASS` 0.56 / 0.83 → **0.62 / 0.83**; `LOOSE_BOX` 0.29 / 0.40 → 0.20 / 0.20; `FALSE_POS` 0.36 / 1.00 (không đổi, dùng `fp_conf` cố định) | Cờ chỉ là **cảnh báo** cho người nên ưu tiên **recall**: chọn mức **cao nhất mà MISSING recall vẫn 1.00** (0.65 đã tụt còn 0.88). Hàng đợi raw 145 → **125** ảnh, ảnh còn cảnh báo 29.3% → **18.8%**. Cái giá: `LOOSE_BOX` recall giảm 0.40 → 0.20 (calib chỉ có 5 ca). Không chọn 0.75–0.8 dù ra Release: MISSING recall tụt 0.88 → 0.75, tức đổi việc bỏ sót lấy hàng đợi vừa ngân sách. |

**Chỗ calibration đánh lừa:** trên calib, `phash_dist = 16` có F1 cao nhất cho `DUP_IMAGE_NEAR` (**0.91**, recall 0.83, precision 1.00).
Nhưng trên raw, mức 16 loại **31/224** ảnh thay vì 22; mở xem 3 cặp raw–raw mới bị cho là trùng thì **2/3 là ảnh khác hẳn nhau**
(`img_0011` người chơi tennis ~ `img_0008` hai người trượt tuyết; `img_0177` người lướt sóng ~ `img_0113` người đàn ông ngồi bàn) → sẽ xoá oan.
Ở mức 20 còn tệ hơn: **134** ảnh bị loại vì "trùng/rò rỉ" (105 bị coi là `LEAK_TEST`), chỉ còn **87/224** ảnh, mà gate lại báo **Release**, vì ảnh đã bị xoá thì không còn cảnh báo để đếm.
Lý do: calib chỉ có **6** ca trùng gần đúng (mỗi ca = 17% recall) và **không có** ca `LEAK_TEST`, nên precision 1.00 trên calib không nói gì về
việc gộp nhầm ảnh khác nhau trên raw. Bài học: số trên calib chỉ để chọn ứng viên, phải chạy trên raw và **mở ảnh ra xem** trước khi chốt.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Gate chặn đúng.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`
(không có người duyệt): kết luận **Rework**, mã thoát **20**, `n_errors = 6` (`MISSING_LABEL_FILE`: img_0031, 0053,
0126, 0135, 0170, 0219), **không xuất** dataset (`work/exp_nb` không được tạo, `exported: null`).
Đối chứng: với ngân sách 80, 6 ảnh này được người gán → 0 lỗi bắt buộc → Hold (mã 10). Máy không bịa nhãn,
nên ảnh chưa gán nhãn luôn chặn pipeline.

**(b) Điểm mù đã biết:**
1. **Ảnh trùng bị cắt mạnh:** `img_0074` ~ `img_0084` (bản sau bị cắt) có phash 16 > 10 nên lọt qua.
   Nâng lên 16 thì bắt được nhưng xoá oan 2 cặp ảnh khác hẳn nhau → không ngưỡng nào vừa bắt được vừa an toàn.
2. **Box lỏng nhẹ:** `LOOSE_BOX` recall chỉ **0.20 (1/5)** trên calib; box lệch nhưng IoU ≥ 0.5 không bao giờ bị cờ.
3. **Checker báo động giả:** sau khi người thay bằng nhãn đúng, checker vẫn cờ **28 lỗi trên 25/80 ảnh đã duyệt**
   (FALSE_POS precision 0.36 trên calib) → không thể để model tự sửa nhãn, chỉ được cảnh báo.
4. **Autofix làm mất vật:** `img_0020` dòng id 93 bị xoá vì id sai, nhưng đó là box một người
   (toạ độ trùng dự đoán MISSING) → máy sửa đúng cú pháp nhưng tạo lỗi thiếu box; chỉ phát hiện nhờ model lớn.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Colab T4, `scripts/train_compare.py`: **yolo26n**, **20 epoch**, imgsz 640, batch 16, **seed 0 và 1** cho mỗi biến thể;
cùng val (`gold_val`, 40 ảnh) và cùng test (`data/test`, 100 ảnh, 387 box). Bảng từ `submission/results/comparison.md`:

| biến thể | #ảnh train | số seed | mAP50 | mAP50-95 | precision | recall |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 202 | 2 | 0.701 ± 0.025 | 0.487 ± 0.008 | 0.759 ± 0.003 | 0.625 ± 0.019 |

**Chênh mAP50 (clean − raw) = −0.025**, xấp xỉ **1 độ lệch chuẩn giữa 2 seed của clean (±0.025)** → **chưa kết luận được**;
trên số liệu, clean **không tốt hơn** raw (mAP50-95 cũng thấp hơn 0.024 ở cả 2 seed).
Theo lớp (AP50 trung bình 2 seed): car 0.738 → 0.738, person 0.822 → 0.823, bus 0.695 → 0.703, nhưng **truck 0.648 → 0.538**
(clean seed 1 chỉ 0.486) → gần như toàn bộ chênh lệch nằm ở một lớp và một seed.

Giả thuyết và cách kiểm:
1. **Model gần như không học từ dữ liệu:** ở cả 4 lần chạy, mAP50 trên val cao nhất ở **epoch 1** (raw 0.801 / 0.800, clean 0.791 / 0.739)
   rồi giảm → `best.pt` ≈ model pretrain COCO sau 1 epoch, nên chất lượng nhãn ít ảnh hưởng tới điểm test.
   Kiểm: train với lr thấp hơn / freeze backbone để val tăng theo epoch, rồi so lại.
2. **Raw được "làm sạch" ngầm và có lợi thế:** Ultralytics tự bỏ **11 ảnh** nhãn hỏng (id 93/−1/7/4, `nan`, thiếu cột, ảnh hỏng),
   nên raw thực sự train **213** ảnh so với **202** của clean; trong đó còn **5 ảnh trùng tập test** (`LEAK_TEST`) làm mAP raw cao giả.
   Kiểm: train lại raw sau khi bỏ 5 ảnh `LEAK_TEST`.
3. **Nhiễu lớn, mẫu nhỏ:** 2 seed, test 100 ảnh; độ lệch clean (±0.025) ngang chênh lệch, lớp truck ít box nên dao động mạnh.
   Kiểm: chạy thêm seed (≥ 5) và xem độ lệch của AP truck.

**Việc tiếp theo:** sửa cấu hình train như (1), bỏ ảnh rò rỉ khỏi raw như (2), thêm seed như (3); và duyệt nốt 38 ảnh còn cảnh báo
để `clean` thật sự sạch trước khi so lại.

## 6. Quyết định và ghi chú AI
**(a) Quyết định: Hold.** `clean_v1` chỉ dùng làm bản nháp để thử nghiệm (vd. train so sánh), **chưa phát hành**.
Điều kiện để thành **Release**: số ảnh còn cảnh báo chưa duyệt phải **≤ 20/202** (< 10%), tức người duyệt cần xem thêm
**ít nhất 18 trong 38 ảnh** còn lại — một vòng duyệt thứ hai ưu tiên `POSSIBLE_LOOSE_BOX` và `POSSIBLE_FALSE_POS`
(hai loại bị bỏ lại nhiều nhất) — rồi chạy lại `python -m pipeline.run`, xác nhận mã thoát 0.
**Không** đi đường tắt: nâng `conf` lên 0.75 cũng ra Release (19/202 = 9.4%) nhưng MISSING recall trên calib tụt 1.00 → 0.88
và chỉ cách ngưỡng 1 ảnh; nâng `phash_dist` lên 20 cũng ra Release nhưng chỉ vì đã xoá 134 ảnh.

**(b) Dùng AI:** có — dùng Claude Code (AI coding agent) để viết cả 4 module, chạy test và phân tích số liệu.
- **Prompt chính:** yêu cầu ngắn theo từng module ("Viết label_format", …); AI đọc docstring + file test của module đó
  (đủ 4 ý: đầu vào, đầu ra, ràng buộc như "ngưỡng đọc từ `cfg`, dòng hỏng không làm chết script", ca biên) rồi mới viết.
- **Cách kiểm:** chạy test từng module rồi `pytest -q` (79 passed); tự thử thêm ca dòng dính 2 lỗi, dòng trống giữa file,
  ảnh nhiều dự đoán (`img_0160`, 53 dự đoán); chạy autofix 2 lần để kiểm idempotent; đối chiếu số lỗi cú pháp với lần quét tay
  (3 `BAD_FORMAT`, 6 `BAD_CLASS_ID`) và với các lỗi tự nhìn thấy (`img_0001` thiếu người, `img_0004` nhãn rỗng có xe).
- **Một lần AI sai:** khi thử `second_opinion` thẳng trên `data/raw` (có ảnh hỏng không nằm trong cache), code gọi model thật,
  tự tải `yolo26l.pt` (50MB) vào repo rồi chết ở ảnh cắt cụt; đã xoá file `.pt` (nằm trong `.gitignore`, chưa commit)
  và chỉ dùng cache. Ngoài ra AI từng gộp 2 module vào 1 commit, trái quy tắc "mỗi module một commit" → đã tách lại.

## Thưởng: check mới `BOX_ASPECT` (lệch tỉ lệ khung hình)
`pipeline/checks/aspect_ratio.py` + `tests/test_aspect_ratio.py` (**8 test**, toàn bộ `pytest -q`: **87 passed**). Cảnh báo (WARN) khi
box có hình dạng vô lý với lớp, tính bằng pixel: **person rộng > 3 lần cao**, hoặc **car/truck/bus có rộng/cao < 0.3**.
Lỗi này các check khác không bắt (box đúng cú pháp, trong ảnh, model lớn vẫn có thể khớp IoU).
- **Chọn ngưỡng từ nhãn người** (`gold_val` + `calib`): chỉ **3/273** box vượt ngưỡng → báo động giả khoảng 1%.
- **Không gắn vào `make run`:** `pipeline/checks/__init__.py` và `configs/pipeline.yaml` là file cố định, nên check chạy riêng
  (`python -m pipeline.checks.aspect_ratio work/run/ds`); ngưỡng đọc từ `cfg["aspect_ratio"]` nếu có, không có thì dùng mặc định.
- **Kết quả:** raw **4/719** box, sau pipeline **3** box. Mở ảnh xem: `img_0159` dòng 4 là một box dẹt ôm cả dãy khán giả
  (đáng sửa); `img_0148` (người bị cắt ở mép trên) và `img_0133` (xe buýt bị cắt ở mép trái) là nhãn hợp lý → điểm mù:
  vật bị cắt ở mép ảnh có tỉ lệ lạ nhưng vẫn đúng, nên check chỉ cảnh báo cho người xem.
