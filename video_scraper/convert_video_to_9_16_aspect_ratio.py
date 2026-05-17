"""9:16 portrait conversion via ffmpeg center-crop.

Previously did a Python frame-by-frame cv2 loop, which was the dominant
runtime cost of the scraper. ffmpeg's `crop` filter runs at native speed
and re-encodes once with hardware-accelerated codecs when available.
"""

import logging
import os
import subprocess

log = logging.getLogger(__name__)


def convert_to_nine_sixteen_aspect_ratio(input_video: str, output_directory: str) -> str:
    """Center-crop `input_video` to 9:16 and write into `output_directory`.

    Returns the absolute output path. Raises RuntimeError on ffmpeg failure.
    """
    os.makedirs(output_directory, exist_ok=True)
    base = os.path.splitext(os.path.basename(input_video))[0]
    output_path = os.path.join(output_directory, f"{base}.mp4")

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", "crop=ih*9/16:ih",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-loglevel", "error",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("ffmpeg portrait failed (code %s):\n%s", result.returncode, result.stderr)
        raise RuntimeError(f"portrait conversion failed for {input_video}")
    return output_path
