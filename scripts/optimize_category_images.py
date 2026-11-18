from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIRS = [
    ROOT / "static" / "images" / "categories",
    ROOT / "static" / "images" / "categories" / "One-Cre8-Media",
]
SINGLE_IMAGES = [
    ROOT / "static" / "images" / "photo1.jpg",
]

sources = set()
for directory in IMAGE_DIRS:
    if directory.exists():
        sources.update(directory.rglob("*.jpg"))
        sources.update(directory.rglob("*.jpeg"))
for path in SINGLE_IMAGES:
    if path.exists():
        sources.add(path)

converted = 0
original_bytes = 0
webp_bytes = 0

for source in sorted(sources):
    destination = source.with_suffix(".webp")
    original_bytes += source.stat().st_size

    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.save(destination, "WEBP", quality=82, method=6)

    webp_bytes += destination.stat().st_size
    converted += 1
    print(f"{source.relative_to(ROOT)}: {source.stat().st_size:,} -> {destination.stat().st_size:,} bytes")

if not converted:
    raise SystemExit("No source JPEG images were found; refusing to report a successful conversion.")

saved = original_bytes - webp_bytes
percent = (saved / original_bytes * 100) if original_bytes else 0
print(f"Converted {converted} images.")
print(f"Original total: {original_bytes:,} bytes")
print(f"WebP total: {webp_bytes:,} bytes")
print(f"Saved: {saved:,} bytes ({percent:.1f}%)")
