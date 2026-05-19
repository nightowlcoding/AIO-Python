from PIL import Image
import os

# Convert the PNG to ICO
png_path = r"C:\Users\arnol\Downloads\payroll app.png"
ico_path = r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\payroll_icon.ico"

# Open the image and resize to standard icon sizes
img = Image.open(png_path)

# Ensure image has alpha channel (for transparency)
if img.mode != 'RGBA':
    img = img.convert('RGBA')

# Save as ICO with multiple resolutions
img.save(ico_path, 'ICO', sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
print(f"Icon created successfully: {ico_path}")
