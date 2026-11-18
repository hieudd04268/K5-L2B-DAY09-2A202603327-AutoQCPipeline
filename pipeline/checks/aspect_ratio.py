"""CHECK THÊM (thưởng) — box lệch tỉ lệ khung hình so với lớp của nó.   BOX_ASPECT (WARN)

Test:  pytest tests/test_aspect_ratio.py -q
Chạy riêng trên một thư mục:  python -m pipeline.checks.aspect_ratio data/raw

Lỗi mà các check khác không bắt: box đúng cú pháp, nằm trong ảnh, nhưng hình dạng vô lý với lớp —
một "person" nằm ngang rộng gấp 3 lần chiều cao, một "car" dựng đứng cao gấp 3 lần chiều rộng.
Thường là box bị kéo méo khi sửa tay, gán nhầm lớp, hoặc chỉ ôm một phần vật. Chỉ CẢNH BÁO: người nằm,
xe bị cắt ở mép ảnh vẫn có thể cho tỉ lệ lạ mà nhãn vẫn đúng → người xem.

Tỉ lệ tính bằng PIXEL: r = (w * rộng_ảnh) / (h * cao_ảnh)  (toạ độ YOLO chuẩn hoá nên phải nhân kích thước ảnh).
- lớp trong `tall_classes` (mặc định: person): r > `tall_max_wh`  → BOX_ASPECT
- các lớp còn lại (xe):                         r < `wide_min_wh`  → BOX_ASPECT

Ngưỡng đọc từ `cfg["aspect_ratio"]` nếu có; không có thì dùng DEFAULTS bên dưới (configs/pipeline.yaml là quy tắc
dự án cố định nên check thưởng không thêm mục vào đó). DEFAULTS chọn offline từ nhãn NGƯỜI (tập val + tập calibration, 273 box; code này không đọc các tập đó):
person ≥ 3.0 hoặc xe ≤ 0.3 chỉ gặp ở 3/273 box (người nằm, xe bị cắt mép) → báo động giả ~1%.

Dòng hỏng / id lạ / w,h ≤ 0 bị bỏ qua (label_format đã báo); ảnh không mở được thì bỏ qua cả ảnh.
"""
from ..common import WARN, Issue, parse_yolo_line

CHECK = "aspect_ratio"
DEFAULTS = {"tall_classes": ["person"], "tall_max_wh": 3.0, "wide_min_wh": 0.3}


def _params(cfg):
    p = dict(DEFAULTS)
    p.update(cfg.get("aspect_ratio") or {})
    return p


def run(ds, cfg):
    p = _params(cfg)
    tall = set(p["tall_classes"])
    issues = []
    for lf in ds.label_files():
        stem = lf.stem
        size = ds.image_size(stem)
        if not size:
            continue                                   # không có ảnh / ảnh hỏng: check khác báo
        W, H = size
        for no, text in ds.read_label_lines(stem) or []:
            try:
                cls, _, _, w, h = parse_yolo_line(text)
            except ValueError:
                continue
            if not 0 <= cls < len(ds.classes) or w <= 0 or h <= 0:
                continue
            name = ds.classes[cls]
            r = (w * W) / (h * H)
            if name in tall and r > p["tall_max_wh"]:
                why = f"{name} rộng gấp {r:.1f} lần cao (> {p['tall_max_wh']})"
            elif name not in tall and r < p["wide_min_wh"]:
                why = f"{name} cao gấp {1 / r:.1f} lần rộng (rộng/cao {r:.3f} < {p['wide_min_wh']})"
            else:
                continue
            issues.append(Issue(CHECK, WARN, "BOX_ASPECT", stem, f"tỉ lệ khung hình lạ: {why}",
                                line=no, extra={"wh": round(r, 3), "class": name}))
    return issues


if __name__ == "__main__":                             # chạy riêng: python -m pipeline.checks.aspect_ratio data/raw
    import sys

    from ..common import Dataset, load_config

    cfg = load_config()
    root = sys.argv[1] if len(sys.argv) > 1 else "data/raw"
    found = run(Dataset(root, cfg["classes"]), cfg)
    print(f"đã quét {root}: {len(found)} box BOX_ASPECT")
    for i in found:
        print(f"[WARN ] BOX_ASPECT  {i.image}.txt:{i.line}  {i.message}")
