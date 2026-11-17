#!/usr/bin/env python3
"""Create smaller WebP copies of OneCre8's static category and hero images."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
IMAGE_ROOT = ROOT / "static" / "images"
CATEGORY_ROOT = IMAGE_ROOT / "categories"
HERO_IMAGE = IMAGE_ROOT / "photo1.jpg"
MAX_EDGE = 1600
WEBP_QUALITY = 82

def optimize(source: Path) -> tuple[int, int]:
    destination = source.with_suffix(".webp")
    with Image.open(source) as original:
        image = original.convert("RGB")
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
        image.save(destination, "WEBP", quality=WEBP_QUALITY, method=6)
    return source.stat().st_size, destination.stat().st_size

def main() -> None:
    sources = sorted(CATEGORY_ROOT.rglob("*.jpg"))
    if HERO_IMAGE.exists():
        sources.append(HERO_IMAGE)
    if not sources:
        raise SystemExit("No source JPEG images were found.")
    original_total = 0
    optimized_total = 0
    for source in sources:
        before, after = optimize(source)
        original_total += before
        optimized_total += after
        print(f"{source.relative_to(ROOT)}: {before:,} -> {after:,} bytes")
    saved = original_total - optimized_total
    percentage = saved / original_total * 100 if original_total else 0
    print(f"\nOptimized {len(sources)} images")
    print(f"Original total: {original_total / 1024 / 1024:.2f} MB")
    print(f"WebP total: {optimized_total / 1024 / 1024:.2f} MB")
    print(f"Saved: {saved / 1024 / 1024:.2f} MB ({percentage:.1f}%)")

if __name__ == "__main__":
    main()
