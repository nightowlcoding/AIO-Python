from PIL import Image, ImageFilter
from rembg import remove
import onnxruntime as ort

# Open image
img = Image.open("/Users/arnoldoramirezjr/Downloads/Tiger_in_the_water.jpg")

# Get subject mask
subject = remove(img)  # subject with transparent background

# Blur original image
blurred = img.filter(ImageFilter.GaussianBlur(radius=2))

# Paste subject onto blurred background
blurred.paste(subject, (0, 0), subject)
blurred.save("output_smart_blur.png")