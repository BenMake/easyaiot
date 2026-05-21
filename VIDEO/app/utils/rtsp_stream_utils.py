"""
RTSP/FFmpeg 拉流共用工具（realtime / snapshot 算法服务对齐）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import cv2


def build_opencv_ffmpeg_capture_options(rtsp_transport: str) -> str:
    transport = (rtsp_transport or "udp").strip().lower()
    if transport not in ("tcp", "udp"):
        transport = "udp"
    return (
        f"rtsp_transport;{transport}"
        "|timeout;10000000"
        "|rw_timeout;5000000"
        "|max_delay;500000"
        "|fflags;nobuffer+discardcorrupt+genpts"
        "|flags;low_delay"
        "|err_detect;ignore_err"
    )


def effective_rtsp_transport(url: str, default: str = "udp") -> str:
    """根据 URL/环境变量选择 rtsp_transport；HEVC/国标场景倾向 tcp。"""
    env = (
        os.getenv("AI_RTSP_TRANSPORT")
        or os.getenv("OPENCV_FFMPEG_RTSP_TRANSPORT")
        or os.getenv("FFMPEG_RTSP_TRANSPORT")
        or ""
    ).strip().lower()
    if env in ("tcp", "udp"):
        return env

    u = (url or "").lower()
    if is_gb28181_source(url) or "hevc" in u or "h265" in u or "h.265" in u:
        return "tcp"
    return (default or "udp").strip().lower() if (default or "udp").strip().lower() in ("tcp", "udp") else "udp"


def gb28181_async_queue_max() -> int:
    try:
        return max(1, min(int((os.getenv("AI_GB28181_ASYNC_QUEUE_MAX", "10") or "10").strip()), 600))
    except ValueError:
        return 10


def is_gb28181_source(source: Optional[str]) -> bool:
    return bool(source and str(source).strip().lower().startswith("gb28181://"))


def task_streams_prefer_tcp(device_streams: Dict[str, Any]) -> bool:
    """任务含 GB28181 或 HEVC 线索时建议 tcp 拉流。"""
    for info in (device_streams or {}).values():
        if info.get("is_gb28181"):
            return True
        url = (info.get("rtsp_url") or "").lower()
        if "hevc" in url or "h265" in url or "h.265" in url:
            return True
        orig = (info.get("original_source") or "")
        if is_gb28181_source(orig):
            return True
    return False


def is_likely_rtsp_flat_corrupt_frame(
    frame,
    std_max: float = 4.0,
    mean_lo: float = 80.0,
    mean_hi: float = 180.0,
) -> bool:
    """判断整帧是否像解码失败后的典型「中灰塌缩」屏。"""
    if frame is None or getattr(frame, "size", 0) == 0:
        return True
    try:
        if len(frame.shape) == 2:
            gray = frame
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _mean, _std = cv2.meanStdDev(gray)
        m, s = float(_mean[0][0]), float(_std[0][0])
        return bool(mean_lo <= m <= mean_hi and s < std_max)
    except Exception:
        return False
