"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, ROOT, parse_yolo_line

DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
CLIP_CODES = {"BOX_OUT_OF_IMAGE"}
REMOVE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}


def _rec(image, line, action, before, after):
    """Một dòng của 03_fixes.csv — đúng 5 khoá (run.py ghi bằng csv.DictWriter)."""
    return {"image": image, "line": "" if line is None else line, "action": action, "before": before, "after": after}


def _clip(text):
    """Cắt box về trong [0,1]. Trả về dòng mới, hoặc None nếu box không còn diện tích (nằm hẳn ngoài ảnh)."""
    cls, cx, cy, w, h = parse_yolo_line(text)
    x1, x2 = max(0.0, cx - w / 2), min(1.0, cx + w / 2)
    y1, y2 = max(0.0, cy - h / 2), min(1.0, cy + h / 2)
    nw, nh = round(x2 - x1, 6), round(y2 - y1, 6)        # làm tròn TRƯỚC khi kiểm, để không ghi ra box 0.000000
    if nw <= 0 or nh <= 0:
        return None
    return f"{cls} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {nw:.6f} {nh:.6f}"


def _remove_image(ds, stem, code):
    """Xoá mọi ảnh trùng stem (bất kể đuôi) + file nhãn. Trả về bản ghi fix, hoặc None nếu không còn gì để xoá."""
    removed = [p.name for p in ds.image_files() if p.stem == stem]
    for p in ds.image_files():
        if p.stem == stem:
            p.unlink()
    lp = ds.label_path(stem)
    if lp.exists():
        lp.unlink()
        removed.append(f"labels/{lp.name}")
    if not removed:
        return None
    return _rec(stem, None, "remove_image", f"{', '.join(removed)} ({code})", "(đã xoá)")


def _rename_classes(ds, cfg):
    """Ghi lại `names` của data.yaml đúng cfg['classes'], giữ nguyên các khoá khác."""
    data = {}
    if ds.yaml_path.exists():
        data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
    before = data.get("names")
    after = {i: n for i, n in enumerate(cfg["classes"])}
    if before == after:
        return None                                       # đã đúng: không làm gì (idempotent)
    data["names"] = after
    ds.yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return _rec("data.yaml", None, "rename_classes", str(before), str(after))


def _fix_lines(ds, stem, drop, clip):
    """Sửa MỘT file nhãn trong một lần ghi. `drop`, `clip`: tập số dòng GỐC (đếm từ 1, kể cả dòng trống)."""
    lp = ds.label_path(stem)
    if not lp.exists():
        return []
    raw = lp.read_text(encoding="utf-8", errors="replace").splitlines()
    out, fixes = [], []
    for no, text in enumerate(raw, 1):                   # cùng cách đánh số với Dataset.read_label_lines
        if no in drop:                                    # xoá dòng thắng cắt box: chỉ ghi 1 fix
            fixes.append(_rec(stem, no, "drop_line", text, "(xoá dòng)"))
            continue
        if no in clip:
            try:
                new = _clip(text)
            except ValueError:                            # dòng không parse được thì không thể cắt: để nguyên, QC vòng sau sẽ báo
                out.append(text)
                continue
            if new is None:
                fixes.append(_rec(stem, no, "drop_line", text, "(xoá dòng: box nằm ngoài ảnh)"))
                continue
            fixes.append(_rec(stem, no, "clip_box", text, new))
            out.append(new)
            continue
        out.append(text)
    if fixes:
        lp.write_text("".join(t + "\n" for t in out), encoding="utf-8")
    return fixes


def fix(ds, issues, cfg):
    raw_dir = (ROOT / "data" / "raw").resolve()
    root = ds.root.resolve()
    if root == raw_dir or raw_dir in root.parents:
        raise ValueError(f"autofix không được sửa dữ liệu gốc: {root}")

    errors = [i for i in issues if i.severity == ERROR]   # cảnh báo (WARN) là việc của người
    fixes = []

    # 1) Loại ảnh trước, để các lỗi dòng của ảnh đó được bỏ qua êm.
    removed = set()
    for i in errors:
        if i.code in REMOVE_CODES and i.image not in removed:
            removed.add(i.image)
            r = _remove_image(ds, i.image, i.code)
            if r:
                fixes.append(r)

    # 2) data.yaml: ghi lại một lần dù có nhiều lỗi BAD_CLASS_NAME.
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        r = _rename_classes(ds, cfg)
        if r:
            fixes.append(r)

    # 3) Gom lỗi dòng theo file; ghi nhận ảnh thiếu nhãn (không tạo file).
    drop, clip, needs = defaultdict(set), defaultdict(set), []
    for i in errors:
        if i.image in removed:
            continue
        if i.code == "MISSING_LABEL_FILE" and i.image not in needs:
            needs.append(i.image)
        elif i.code in DROP_CODES and i.line is not None:
            drop[i.image].add(i.line)
        elif i.code in CLIP_CODES and i.line is not None:
            clip[i.image].add(i.line)

    for stem in needs:
        if not ds.label_path(stem).exists():
            fixes.append(_rec(stem, None, "needs_label", "(không có file)", "chuyển người gán"))

    for stem in sorted(set(drop) | set(clip)):
        fixes.extend(_fix_lines(ds, stem, drop[stem], clip[stem]))

    return fixes
