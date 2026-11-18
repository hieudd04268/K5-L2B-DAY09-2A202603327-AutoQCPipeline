"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


CHECK = "label_format"


def _overflow(cx, cy, w, h) -> float:
    """Mức tràn lớn nhất (tỉ lệ ảnh) của box ra ngoài [0, 1] ở cả 4 mép; 0 nếu nằm trong ảnh."""
    left, right = cx - w / 2, cx + w / 2
    top, bottom = cy - h / 2, cy + h / 2
    return max(0.0, -left, right - 1.0, -top, bottom - 1.0)


def run(ds, cfg):
    c = cfg["label_format"]
    tol, min_px = c["overflow_tol"], c["min_box_px"]
    max_frac, dup_iou = c["max_box_frac"], c["dup_box_iou"]
    n_cls = len(ds.classes)
    issues = []

    for lf in ds.label_files():
        stem = lf.stem
        size = ds.image_size(stem)             # None nếu không có ảnh / ảnh hỏng -> bỏ qua BOX_TINY
        kept = []                              # (số dòng, box) các dòng hợp lệ phía trước, để so DUP_BOX

        for no, text in ds.read_label_lines(stem) or []:   # số dòng gốc, đã bỏ dòng trống
            # 1) cú pháp: 5 cột số, không nan/inf
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError as e:
                issues.append(Issue(CHECK, ERROR, "BAD_FORMAT", stem, f"dòng không đúng 5 cột số: {e}", line=no))
                continue
            # 2) id lớp
            if not 0 <= cls < n_cls:
                issues.append(Issue(CHECK, ERROR, "BAD_CLASS_ID", stem, f"id lớp {cls} ngoài 0..{n_cls - 1}",
                                    line=no, extra={"class": cls}))
                continue
            # 3) box rỗng
            if w <= 0 or h <= 0:
                issues.append(Issue(CHECK, ERROR, "BOX_ZERO", stem, f"box rộng/cao <= 0 (w={w}, h={h})", line=no))
                continue

            # 4) hình học: các kiểm tra dưới đây độc lập, một dòng có thể dính nhiều mã
            box = (cx, cy, w, h)
            over = _overflow(*box)
            if over > tol:
                issues.append(Issue(CHECK, ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ra ngoài ảnh {over:.4f} (> {tol})",
                                    line=no, extra={"overflow": round(over, 6)}))

            dup = next((pno for pno, (pcls, pbox) in kept if pcls == cls and iou_xywh(pbox, box) > dup_iou), None)
            if dup is not None:
                issues.append(Issue(CHECK, ERROR, "DUP_BOX", stem, f"trùng box cùng lớp với dòng {dup}",
                                    line=no, extra={"of_line": dup}))

            if size:
                W, H = size
                short = min(w * W, h * H)
                if short < min_px:
                    issues.append(Issue(CHECK, WARN, "BOX_TINY", stem, f"cạnh ngắn {short:.1f}px < {min_px}px",
                                        line=no, extra={"short_px": round(short, 1)}))

            if w * h > max_frac:
                issues.append(Issue(CHECK, WARN, "BOX_HUGE", stem, f"box phủ {w * h:.0%} ảnh (> {max_frac:.0%})",
                                    line=no, extra={"area_frac": round(w * h, 4)}))

            kept.append((no, (cls, box)))

    return issues
