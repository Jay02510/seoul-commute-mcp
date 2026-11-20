"""Seoul Commute logo: subway line with stations, a sun, and air-quality dots."""
from PIL import Image, ImageDraw, ImageFilter

S = 2048  # draw big, downscale for smooth edges
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Background: rounded square, deep night-blue gradient
bg = Image.new("RGBA", (S, S))
bd = ImageDraw.Draw(bg)
top, bot = (22, 35, 74), (12, 20, 46)
for y in range(S):
    t = y / S
    c = tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)) + (255,)
    bd.line([(0, y), (S, y)], fill=c)
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=440, fill=255)
img.paste(bg, (0, 0), mask)
d = ImageDraw.Draw(img)

# Sun (top right) with soft glow
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(glow).ellipse([1210, 330, 1710, 830], fill=(255, 196, 70, 120))
glow = glow.filter(ImageFilter.GaussianBlur(70))
img.alpha_composite(glow)
d = ImageDraw.Draw(img)
d.ellipse([1300, 420, 1620, 740], fill=(255, 200, 72, 255))

# Fine-dust dots (left top): three small dots in calm teal
for (x, y, r) in [(470, 560, 46), (610, 470, 30), (650, 650, 38)]:
    d.ellipse([x - r, y - r, x + r, y + r], fill=(120, 214, 200, 230))

# Subway line: one bold path with a bend, rounded joints
W = 150
path = [(440, 1480), (900, 1480), (1200, 1180), (1620, 1180)]
line_col = (72, 199, 116, 255)
d.line(path, fill=line_col, width=W, joint="curve")
for (x, y) in (path[0], path[-1]):  # round caps
    d.ellipse([x - W / 2, y - W / 2, x + W / 2, y + W / 2], fill=line_col)

# Stations: white rings with dark centers
def station(x, y, big=False):
    R = 120 if big else 92
    r = 60 if big else 44
    d.ellipse([x - R, y - R, x + R, y + R], fill=(255, 255, 255, 255))
    d.ellipse([x - r, y - r, x + r, y + r], fill=(18, 28, 62, 255))

station(440, 1480, big=True)
station(700, 1480)
station(1380, 1180)
station(1620, 1180, big=True)

img = img.resize((512, 512), Image.LANCZOS)
img.save("seoul-commute-logo.png")
print("saved", img.size)
