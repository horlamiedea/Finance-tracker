import pytesseract
from PIL import Image
# import numpy as np

class OCRService:
    @staticmethod
    def extract_text(image_path):
        # 1) Open the file explicitly with Pillow
        try:
            image = Image.open(image_path)
        except Exception as e:
            raise RuntimeError(f"Unable to open image {image_path}: {e}")

        # 2) Log what you actually got back
        print(f"[OCRService] loaded image: {image!r}, mode={image.mode}, format={image.format}")

        # 3) Convert to a supported mode (RGB or L)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
            print(f"[OCRService] converted to mode: {image.mode}")

        # 4) Optionally turn it into a NumPy array (bypass some PIL internals)
        img_array = np.array(image)

        # 5) Run Tesseract on the array
        text = pytesseract.image_to_string(img_array)

        return text
