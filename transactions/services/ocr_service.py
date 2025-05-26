import pytesseract
from PIL import Image
import numpy as np

class OCRService:
    @staticmethod
    def extract_text(image_path):
        # 1) Open the file explicitly with Pillow
        try:
            image = Image.open(image_path)
        except Exception as e:
            raise RuntimeError(f"Unable to open image {image_path}: {e}")
        print(f"[OCRService] loaded image: {image!r}, mode={image.mode}, format={image.format}")

        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
            print(f"[OCRService] converted to mode: {image.mode}")

        img_array = np.array(image)
        text = pytesseract.image_to_string(img_array)
        return text
