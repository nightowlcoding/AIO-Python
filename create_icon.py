from PIL import Image, ImageDraw, ImageFont
import os

# Create a 256x256 icon with Payroll design
size = 256
img = Image.new('RGB', (size, size), color='white')
draw = ImageDraw.Draw(img)

# Fill with gradient-like pattern (blue tones)
dark_blue = (25, 103, 210)
light_blue = (63, 135, 245)

for i in range(size):
    ratio = i / size
    r = int(25 + (63-25) * ratio)
    g = int(103 + (135-103) * ratio)
    b = int(210 + (245-210) * ratio)
    draw.line([(0, i), (size, i)], fill=(r, g, b))

# Draw dollar sign
font_size = 120
try:
    font = ImageFont.truetype("arial.ttf", font_size)
except:
    font = ImageFont.load_default()

# Draw dollar sign in white
draw.text((size//2 - 40, size//2 - 60), "$", fill='white', font=font)

# Draw lines under dollar sign to represent document
line_y = size//2 + 40
for i in range(3):
    draw.line([(size//2 - 40, line_y + i*12), (size//2 + 40, line_y + i*12)], fill='white', width=3)

# Save as ICO
icon_path = os.path.join(os.getcwd(), 'payroll_icon.ico')
img.save(icon_path, 'ICO', sizes=[(256, 256)])
print(f"Icon created: {icon_path}")
