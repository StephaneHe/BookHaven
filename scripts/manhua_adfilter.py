#!/usr/bin/env python3
"""Ad/banner detection for manhua page images.

roliascan bakes promo banners into the page stream (e.g. a recurring 728x90
"BEST WEBSITE TO WATCH MOVIES" ad, plus thin LIKEMANGA.IO / WEBNOVEL watermark
strips). Real webtoon panels are tall (aspect ratio well below 1); ad/watermark
banners are wide-and-short. We drop an image when it is either a known IAB ad
size or a wide, short banner strip — never a content panel (verified: content
tail-slices on this title are >=196 px tall).
"""
from PIL import Image

# Standard IAB banner dimensions — never a manhua content panel.
AD_SIZES = {
    (728, 90), (728, 190), (970, 90), (970, 250), (468, 60),
    (320, 50), (320, 100), (300, 250), (336, 280), (300, 600),
    (160, 600), (250, 250), (300, 100),
}

# Wide+short banner heuristic (catches re-encoded ads and watermark strips).
MIN_BANNER_AR = 3.0      # width/height
MAX_BANNER_H = 120       # px; content panels that are wide are still taller


def image_size(path):
    with Image.open(path) as im:
        return im.size


def is_ad_image(path):
    """True if the image at `path` looks like an ad/watermark banner."""
    try:
        w, h = image_size(path)
    except Exception:
        return False
    if not h:
        return False
    if (w, h) in AD_SIZES:
        return True
    if w / h >= MIN_BANNER_AR and h <= MAX_BANNER_H:
        return True
    return False
