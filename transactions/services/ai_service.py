from openai import OpenAI
import os
import re
import json
from datetime import datetime
import base64

class AIService:
    def __init__(self, api_key: str = None):
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self.client = OpenAI(api_key=api_key)

    def categorize_expenses_from_image(self, image_path: str) -> dict:
        """
        Send the receipt image directly to a vision-capable chat model (GPT-4-Vision)
        and extract a JSON object with keys:
          - date  : "YYYY-MM-DD"
          - total : number
          - items : [ {description: str, amount: number}, … ]

        Returns:
            A Python dict with the above structure.
        Raises:
            ValueError if the model response can’t be parsed into JSON.
        """

        # 1) Load and base64-encode the image
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        b64 = base64.b64encode(img_bytes).decode()

        # 2) Build our prompt
        system_msg = {
            "role": "system",
            "content": (
                "You are a JSON extractor for store receipts. "
                "When you receive an image of a receipt, you must output **only** valid JSON "
                "with exactly these keys:\n"
                "  • date   : string in YYYY-MM-DD format\n"
                "  • total  : number\n"
                "  • items  : array of objects, each with\n"
                "       – description : string\n"
                "       – amount      : number\n"
                "Do not add any extra fields or explanations."
            )
        }

        instruction_msg = {
            "role": "user",
            # a brief instruction before the image
            "content": "Please extract the date, total, and line items from this receipt image:"
        }

        image_msg = {
            "role": "user",
            # embed the image as a data URL
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "alt_text": "photo of a store receipt"
                    }
                }
            ]
        }

        # 3) Call the chat API with vision
        resp = self.client.chat.completions.create(
            model="gpt-4o-mini",        # or whichever GPT-4 vision model you have access to
            messages=[system_msg, instruction_msg, image_msg],
            temperature=0.0,
            max_tokens=300
        )

        raw = resp.choices[0].message.content

        # 4) Strip any markdown fences and parse JSON
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"Could not parse JSON from model reply:\n{raw}") from e

        # 5) Basic validation
        for key in ("date", "total", "items"):
            if key not in data:
                raise ValueError(f"Missing key `{key}` in parsed data: {data}")

        return data