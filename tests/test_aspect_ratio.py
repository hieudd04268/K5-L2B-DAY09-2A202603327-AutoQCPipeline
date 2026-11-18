"""Test cho check thưởng `aspect_ratio` (BOX_ASPECT). File test MỚI — không sửa test có sẵn."""
from pipeline.checks import aspect_ratio


def run(make_ds, cfg, lines, size=(640, 480)):
    ds = make_ds(images={"a": 1}, labels={"a": lines}, size=size)
    return [(i.code, i.line) for i in aspect_ratio.run(ds, cfg)]


def test_normal_shapes_are_silent(make_ds, cfg):
    # person đứng (cao hơn rộng), car nằm ngang: đúng hình dạng thường gặp
    assert run(make_ds, cfg, ["1 0.5 0.5 0.1 0.4", "0 0.3 0.7 0.3 0.15"]) == []


def test_wide_person_is_flagged(make_ds, cfg):
    # 0.5*640 / (0.1*480) = 6.7 > 3
    assert run(make_ds, cfg, ["1 0.5 0.5 0.1 0.4", "1 0.5 0.5 0.5 0.1"]) == [("BOX_ASPECT", 2)]


def test_tall_vehicle_is_flagged_for_every_non_person_class(make_ds, cfg):
    # 0.05*640 / (0.6*480) = 0.11 < 0.3 cho car, truck, bus
    lines = [f"{c} 0.5 0.5 0.05 0.6" for c in (0, 2, 3)]
    assert run(make_ds, cfg, lines) == [("BOX_ASPECT", 1), ("BOX_ASPECT", 2), ("BOX_ASPECT", 3)]


def test_ratio_is_computed_in_pixels(make_ds, cfg):
    # cùng toạ độ chuẩn hoá: ảnh ngang 4:1 -> person rộng 4 lần cao (cờ); ảnh dọc 1:4 -> không cờ
    assert run(make_ds, cfg, ["1 0.5 0.5 0.2 0.2"], size=(640, 160)) == [("BOX_ASPECT", 1)]
    assert run(make_ds, cfg, ["1 0.5 0.5 0.2 0.2"], size=(160, 640)) == []


def test_thresholds_come_from_config(make_ds, cfg):
    cfg["aspect_ratio"] = {"tall_max_wh": 10.0}
    assert run(make_ds, cfg, ["1 0.5 0.5 0.5 0.1"]) == []
    cfg["aspect_ratio"] = {"tall_classes": [], "wide_min_wh": 0.3}          # person cũng coi như xe
    assert run(make_ds, cfg, ["1 0.5 0.5 0.05 0.6"]) == [("BOX_ASPECT", 1)]


def test_broken_lines_do_not_crash_and_keep_line_numbers(make_ds, cfg):
    lines = ["garbage", "", "93 0.5 0.5 0.5 0.1", "1 0.5 0.5 0 0.1", "1 nan 0.5 0.5 0.1", "1 0.5 0.5 0.5 0.1"]
    assert run(make_ds, cfg, lines) == [("BOX_ASPECT", 6)]


def test_label_without_image_is_skipped(make_ds, cfg):
    ds = make_ds(images={"a": 1}, labels={"a": ["1 0.5 0.5 0.1 0.4"], "orphan": ["1 0.5 0.5 0.9 0.05"]})
    assert aspect_ratio.run(ds, cfg) == []


def test_issues_are_warnings_with_ratio_in_extra(make_ds, cfg):
    ds = make_ds(images={"a": 1}, labels={"a": ["1 0.5 0.5 0.5 0.1"]}, size=(640, 480))
    (i,) = aspect_ratio.run(ds, cfg)
    assert i.severity == "warn" and i.image == "a" and abs(i.extra["wh"] - 6.667) < 0.01 and i.extra["class"] == "person"
