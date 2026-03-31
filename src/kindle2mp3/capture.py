from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import time

from AppKit import NSBitmapImageRep, NSPNGFileType
from PIL import Image, ImageChops, ImageOps, ImageStat
import Quartz

from kindle2mp3.windowing import WindowInfo


@dataclass(slots=True)
class KeyPressProbeResult:
    key_name: str
    key_code: int
    transport: str
    baseline_path: Path
    candidate_path: Path
    diff_score: float
    frontmost_before: str | None
    frontmost_after: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "key_name": self.key_name,
            "key_code": self.key_code,
            "transport": self.transport,
            "baseline_path": str(self.baseline_path),
            "candidate_path": str(self.candidate_path),
            "diff_score": self.diff_score,
            "frontmost_before": self.frontmost_before,
            "frontmost_after": self.frontmost_after,
        }


@dataclass(slots=True)
class CaptureRunResult:
    key_name: str
    key_code: int
    transport: str
    output_dir: Path
    saved_paths: list[Path]

    def to_dict(self) -> dict[str, object]:
        return {
            "key_name": self.key_name,
            "key_code": self.key_code,
            "transport": self.transport,
            "output_dir": str(self.output_dir),
            "saved_paths": [str(path) for path in self.saved_paths],
            "page_count": len(self.saved_paths),
        }


class WindowCapture:
    def save_window_screenshot(self, window: WindowInfo, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        try:
            return self._save_window_only(window, output)
        except RuntimeError:
            return self._save_cropped_display(window, output)

    def _save_window_only(self, window: WindowInfo, output: Path) -> Path:
        cmd = ["screencapture", "-x", "-l", str(window.window_id), str(output)]
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                f"screencapture failed for window {window.window_id}: {completed.stderr.strip()}"
            )
        if not output.exists():
            raise RuntimeError(f"screencapture did not create {output}")
        return output

    def _save_cropped_display(self, window: WindowInfo, output: Path) -> Path:
        image = Quartz.CGWindowListCreateImage(
            Quartz.CGRectInfinite,
            Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
            Quartz.kCGWindowImageDefault,
        )
        if image is None:
            raise RuntimeError("Quartz full-screen capture failed")

        png_bytes = cgimage_to_png_bytes(image)
        output.write_bytes(png_bytes)

        with Image.open(output) as screenshot:
            cropped = crop_window_region(screenshot, window)
            cropped.save(output)
        return output


class KeyPressProbe:
    def __init__(self, *, settle_delay: float = 1.0, transport: str = "system_events") -> None:
        self.capture = WindowCapture()
        self.settle_delay = settle_delay
        self.transport = transport

    def probe(
        self,
        window: WindowInfo,
        *,
        key_name: str,
        key_code: int,
        output_dir: str | Path,
    ) -> KeyPressProbeResult:
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)

        activate_kindle()
        time.sleep(0.4)
        frontmost_before = get_frontmost_app_name()

        baseline_path = self.capture.save_window_screenshot(window, directory / "baseline.png")
        post_key_press(key_code, transport=self.transport)
        time.sleep(self.settle_delay)

        candidate_path = self.capture.save_window_screenshot(window, directory / f"after_{key_name}.png")
        frontmost_after = get_frontmost_app_name()
        diff_score = compute_content_difference(baseline_path, candidate_path)

        return KeyPressProbeResult(
            key_name=key_name,
            key_code=key_code,
            transport=self.transport,
            baseline_path=baseline_path,
            candidate_path=candidate_path,
            diff_score=diff_score,
            frontmost_before=frontmost_before,
            frontmost_after=frontmost_after,
        )


class PageCaptureRunner:
    def __init__(
        self,
        *,
        settle_delay: float = 1.0,
        transport: str = "system_events",
        min_diff_score: float = 0.01,
    ) -> None:
        self.capture = WindowCapture()
        self.settle_delay = settle_delay
        self.transport = transport
        self.min_diff_score = min_diff_score

    def run(
        self,
        window: WindowInfo,
        *,
        key_name: str,
        key_code: int,
        output_dir: str | Path,
        pages: int,
    ) -> CaptureRunResult:
        if pages <= 0:
            raise ValueError("pages must be greater than zero")

        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)

        activate_kindle()
        time.sleep(0.4)

        saved_paths: list[Path] = []
        first_path = directory / build_page_filename(1)
        self.capture.save_window_screenshot(window, first_path)
        saved_paths.append(first_path)

        previous_path = first_path
        for page_number in range(2, pages + 1):
            activate_kindle()
            time.sleep(0.2)
            post_key_press(key_code, transport=self.transport)
            time.sleep(self.settle_delay)

            next_path = directory / build_page_filename(page_number)
            self.capture.save_window_screenshot(window, next_path)
            diff_score = compute_content_difference(previous_path, next_path)
            if diff_score < self.min_diff_score:
                next_path.unlink(missing_ok=True)
                raise RuntimeError(
                    f"page turn did not change the page at step {page_number - 1}: diff={diff_score:.6f}"
                )
            saved_paths.append(next_path)
            previous_path = next_path

        return CaptureRunResult(
            key_name=key_name,
            key_code=key_code,
            transport=self.transport,
            output_dir=directory,
            saved_paths=saved_paths,
        )


def compute_image_difference(left_path: str | Path, right_path: str | Path, *, size: int = 64) -> float:
    with Image.open(left_path) as left_image, Image.open(right_path) as right_image:
        left = ImageOps.grayscale(left_image).resize((size, size))
        right = ImageOps.grayscale(right_image).resize((size, size))
        diff = ImageChops.difference(left, right)
        stat = ImageStat.Stat(diff)
        return float(stat.mean[0]) / 255.0


def compute_content_difference(left_path: str | Path, right_path: str | Path, *, size: int = 64) -> float:
    with Image.open(left_path) as left_image, Image.open(right_path) as right_image:
        left = ImageOps.grayscale(crop_content_region(left_image)).resize((size, size))
        right = ImageOps.grayscale(crop_content_region(right_image)).resize((size, size))
        diff = ImageChops.difference(left, right)
        stat = ImageStat.Stat(diff)
        return float(stat.mean[0]) / 255.0


def post_left_click(x: int, y: int) -> None:
    move_event = Quartz.CGEventCreateMouseEvent(
        None,
        Quartz.kCGEventMouseMoved,
        (x, y),
        Quartz.kCGMouseButtonLeft,
    )
    down_event = Quartz.CGEventCreateMouseEvent(
        None,
        Quartz.kCGEventLeftMouseDown,
        (x, y),
        Quartz.kCGMouseButtonLeft,
    )
    up_event = Quartz.CGEventCreateMouseEvent(
        None,
        Quartz.kCGEventLeftMouseUp,
        (x, y),
        Quartz.kCGMouseButtonLeft,
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, move_event)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down_event)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up_event)


def compute_click_point(
    window: WindowInfo,
    *,
    side: str,
    columns: int = 8,
) -> tuple[int, int]:
    if side not in {"left", "right"}:
        raise ValueError(f"Unsupported side: {side}")
    if columns <= 1:
        raise ValueError("columns must be greater than one")

    column_width = window.width / columns
    y = int(window.bounds["Y"] + (window.height / 2))
    if side == "left":
        x = int(window.bounds["X"] + (column_width / 2))
    else:
        x = int(window.bounds["X"] + window.width - (column_width / 2))
    return x, y


def click_window_point(window: WindowInfo, *, side: str) -> tuple[int, int]:
    x, y = compute_click_point(window, side=side)
    post_left_click(x, y)
    return x, y


def build_page_filename(page_number: int) -> str:
    return f"page_{page_number:06d}.png"


def post_key_press(key_code: int, *, transport: str = "system_events") -> None:
    if transport == "system_events":
        post_system_events_key_code(key_code)
        return
    if transport != "cgevent":
        raise ValueError(f"Unsupported key transport: {transport}")

    post_cgevent_key_press(key_code)


def post_cgevent_key_press(key_code: int) -> None:
    down_event = Quartz.CGEventCreateKeyboardEvent(None, key_code, True)
    up_event = Quartz.CGEventCreateKeyboardEvent(None, key_code, False)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down_event)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up_event)


def post_system_events_key_code(key_code: int) -> None:
    completed = subprocess.run(
        ["osascript", "-e", f'tell application "System Events" to key code {key_code}', "-e", "delay 0.1"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"System Events key code failed: {completed.stderr.strip()}")


def activate_kindle() -> None:
    subprocess.run(
        ["osascript", "-e", 'tell application id "com.amazon.Lassen" to activate', "-e", "delay 0.8"],
        check=True,
        capture_output=True,
        text=True,
    )


def get_frontmost_app_name() -> str | None:
    script = 'tell application "System Events" to get name of first application process whose frontmost is true'
    completed = subprocess.run(
        ["osascript", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def crop_window_region(image: Image.Image, window: WindowInfo) -> Image.Image:
    display_bounds = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
    scale_x = image.width / int(display_bounds.size.width)
    scale_y = image.height / int(display_bounds.size.height)

    left = max(0, int(window.bounds["X"] * scale_x))
    top = max(0, int(window.bounds["Y"] * scale_y))
    right = min(image.width, int((window.bounds["X"] + window.width) * scale_x))
    bottom = min(image.height, int((window.bounds["Y"] + window.height) * scale_y))

    if right <= left or bottom <= top:
        raise RuntimeError(
            f"Invalid crop bounds for window {window.window_id}: {(left, top, right, bottom)}"
        )
    return image.crop((left, top, right, bottom))


def crop_content_region(image: Image.Image) -> Image.Image:
    width, height = image.size
    left = int(width * 0.18)
    top = int(height * 0.12)
    right = int(width * 0.82)
    bottom = int(height * 0.88)
    return image.crop((left, top, right, bottom))


def cgimage_to_png_bytes(image) -> bytes:
    bitmap = NSBitmapImageRep.alloc().initWithCGImage_(image)
    data = bitmap.representationUsingType_properties_(NSPNGFileType, None)
    if data is None:
        raise RuntimeError("Failed to convert Quartz image to PNG data")
    return bytes(data)
