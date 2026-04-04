from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from kindle2mp3.layout import LayoutAnalyzer, TextGroup, load_ocr_raw


GROUP_COLORS = [
    (46, 204, 113),
    (52, 152, 219),
    (231, 76, 60),
    (241, 196, 15),
    (155, 89, 182),
    (230, 126, 34),
    (26, 188, 156),
    (192, 57, 43),
    (41, 128, 185),
    (142, 68, 173),
]

NOISE_COLOR = (180, 180, 180)


def render_groups_on_image(
    image_path: str | Path,
    all_groups: list[TextGroup],
    body_groups: list[TextGroup],
    output_path: str | Path,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    body_ids = {g.group_id for g in body_groups}

    with Image.open(image_path) as img:
        overlay = img.copy().convert("RGBA")
        draw = ImageDraw.Draw(overlay)

        for group in all_groups:
            is_body = group.group_id in body_ids
            if is_body:
                color = GROUP_COLORS[group.group_id % len(GROUP_COLORS)]
            else:
                color = NOISE_COLOR

            bb = group.bounding_box
            fill_color = (*color, 40)
            outline_color = (*color, 200)
            draw.rectangle(
                [bb.left, bb.top, bb.right, bb.bottom],
                fill=fill_color,
                outline=outline_color,
                width=2,
            )

            for box in group.boxes:
                b = box.bbox
                draw.rectangle(
                    [b.left, b.top, b.right, b.bottom],
                    outline=(*color, 160),
                    width=1,
                )

            label = f"G{group.group_id}"
            if is_body:
                label += " [BODY]"
            else:
                label += " [noise]"
            label += f" ({group.total_chars}ch, {len(group.boxes)}box)"

            draw.text(
                (bb.left + 2, bb.top - 14),
                label,
                fill=(*color, 255),
            )

        overlay.save(str(output))
    return output


def debug_session_layout(
    raw_dir: Path,
    image_dir: Path,
    output_dir: Path,
    *,
    analyzer: LayoutAnalyzer | None = None,
) -> list[Path]:
    if analyzer is None:
        analyzer = LayoutAnalyzer()

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for raw_path in sorted(raw_dir.glob("page_*.json")):
        stem = raw_path.stem
        image_path = image_dir / f"{stem}.png"
        if not image_path.exists():
            continue

        lines = load_ocr_raw(raw_path)
        boxes = analyzer.parse_boxes(lines)

        with Image.open(image_path) as img:
            page_height = img.height

        all_groups = analyzer.group_boxes(boxes)
        body_groups = analyzer.classify_groups(all_groups, page_height=page_height)

        output_path = output_dir / f"{stem}_layout.png"
        render_groups_on_image(image_path, all_groups, body_groups, output_path)
        results.append(output_path)

    return results
