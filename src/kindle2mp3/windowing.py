from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import platform
from typing import Iterable

try:
    import Quartz
except ImportError:  # pragma: no cover - exercised on unsupported setups
    Quartz = None


@dataclass(slots=True)
class WindowInfo:
    window_id: int
    owner_name: str
    owner_pid: int
    title: str
    bounds: dict[str, int]
    layer: int
    alpha: float
    on_screen: bool

    @property
    def width(self) -> int:
        return int(self.bounds.get("Width", 0))

    @property
    def height(self) -> int:
        return int(self.bounds.get("Height", 0))

    @property
    def area(self) -> int:
        return self.width * self.height

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["width"] = self.width
        payload["height"] = self.height
        payload["area"] = self.area
        return payload


class WindowingUnavailableError(RuntimeError):
    """Raised when the macOS window APIs are not available."""


class MacOSWindowDetector:
    def __init__(self) -> None:
        if platform.system() != "Darwin":
            raise WindowingUnavailableError("macOS window detection is only supported on Darwin")
        if Quartz is None:
            raise WindowingUnavailableError(
                "pyobjc Quartz bindings are not installed. Run `uv sync` first."
            )

    def list_windows(
        self,
        *,
        on_screen_only: bool = True,
        min_width: int = 200,
        min_height: int = 200,
    ) -> list[WindowInfo]:
        raw_windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionAll,
            Quartz.kCGNullWindowID,
        )
        windows: list[WindowInfo] = []

        for raw in raw_windows:
            info = self._parse_window(raw)
            if info is None:
                continue
            if on_screen_only and not info.on_screen:
                continue
            if info.width < min_width or info.height < min_height:
                continue
            windows.append(info)

        windows.sort(key=lambda item: (item.owner_name.lower(), -item.area, item.window_id))
        return windows

    def find_kindle_windows(self) -> list[WindowInfo]:
        return self.find_windows(app_names=("Kindle",))

    def find_windows(
        self,
        *,
        app_names: tuple[str, ...],
        title_keywords: tuple[str, ...] = (),
    ) -> list[WindowInfo]:
        candidates: list[WindowInfo] = []
        for window in self.list_windows():
            owner = window.owner_name.casefold()
            title = window.title.casefold()
            if any(app.casefold() == owner for app in app_names):
                candidates.append(window)
                continue
            if title_keywords and any(keyword.casefold() in title for keyword in title_keywords):
                candidates.append(window)
        candidates.sort(key=lambda item: (-item.area, item.window_id))
        return candidates

    def detect_primary_kindle_window(self) -> WindowInfo | None:
        windows = self.find_kindle_windows()
        return windows[0] if windows else None

    @staticmethod
    def dumps(windows: Iterable[WindowInfo]) -> str:
        return json.dumps([window.to_dict() for window in windows], ensure_ascii=False, indent=2)

    def _parse_window(self, raw: dict[object, object]) -> WindowInfo | None:
        owner_name = str(raw.get(Quartz.kCGWindowOwnerName, "")).strip()
        title = str(raw.get(Quartz.kCGWindowName, "")).strip()
        bounds = raw.get(Quartz.kCGWindowBounds, {})
        layer = int(raw.get(Quartz.kCGWindowLayer, 0))
        alpha = float(raw.get(Quartz.kCGWindowAlpha, 1.0))
        on_screen_raw = raw.get(Quartz.kCGWindowIsOnscreen)
        on_screen = True if on_screen_raw is None else bool(on_screen_raw)
        window_id = int(raw.get(Quartz.kCGWindowNumber, 0))
        owner_pid = int(raw.get(Quartz.kCGWindowOwnerPID, 0))

        if not owner_name or bounds is None:
            return None
        if layer != 0:
            return None
        if alpha <= 0.0:
            return None

        normalized_bounds = {
            "X": int(bounds.get("X", 0)),
            "Y": int(bounds.get("Y", 0)),
            "Width": int(bounds.get("Width", 0)),
            "Height": int(bounds.get("Height", 0)),
        }
        return WindowInfo(
            window_id=window_id,
            owner_name=owner_name,
            owner_pid=owner_pid,
            title=title,
            bounds=normalized_bounds,
            layer=layer,
            alpha=alpha,
            on_screen=on_screen,
        )
