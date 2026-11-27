"""Generate the deterministic square artwork opened through the editor file input."""
import sys

from PIL import Image, ImageDraw


image = Image.new("RGBA", (1600, 1600), (241, 230, 210, 255))
draw = ImageDraw.Draw(image)
for offset in range(0, 700, 9):
    colour = (30 + offset % 180, 65 + offset % 110, 99 + offset % 130, 255)
    draw.ellipse((offset, offset, 1599 - offset, 1599 - offset), outline=colour, width=4)
draw.polygon([(800, 230), (1320, 1180), (280, 1180)], fill=(31, 120, 128, 255))
image.save(sys.argv[1])
