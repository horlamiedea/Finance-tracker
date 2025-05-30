from openai import OpenAI
import os
import re
import json
from datetime import datetime
import base64
from typing import Optional, Dict, Any
import logging
logger = logging.getLogger(__name__)    

class AIService:
    def __init__(self, api_key: str = None):
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self.client = OpenAI(api_key=api_key)

    def categorize_expenses_from_image(self, image_path: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Send the receipt image to a vision-capable chat model (GPT-4-Vision)
        and extract a JSON object with keys:
          - date  : "YYYY-MM-DD"
          - total : number
          - items : [ {description: str, amount: number}, … ]

        Args:
            image_path: Path to the receipt image.
            max_retries: Number of retries for API calls if JSON is invalid.

        Returns:
            A Python dict with the above structure.

        Raises:
            ValueError if the model response can’t be parsed into JSON after retries or repair.
        """
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        b64 = base64.b64encode(img_bytes).decode()

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
                "Ensure the JSON is complete, valid, and includes all items from the receipt. "
                "Do not truncate the output or include partial items."
            )
        }

        instruction_msg = {
            "role": "user",
            "content": "Please extract the date, total, and all line items from this receipt image:"
        }

        image_msg = {
            "role": "user",
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

        for attempt in range(max_retries):
            try:
                logger.info(f"Attempt {attempt + 1} to process receipt image")
                resp = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[system_msg, instruction_msg, image_msg],
                    temperature=0.0,
                    max_tokens=500  # Increased to handle larger receipts
                )

                raw = resp.choices[0].message.content
                logger.info(f"Raw API response:\n{raw}")
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()

                try:
                    data = json.loads(cleaned)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse failed: {str(e)}. Attempting repair.")
                    repaired_json = self._repair_json(cleaned)
                    logger.info(f"Repaired JSON:\n{repaired_json}")
                    try:
                        data = json.loads(repaired_json)
                    except json.JSONDecodeError as e2:
                        logger.error(f"Repair failed: {str(e2)}")
                        if attempt < max_retries - 1:
                            continue  # Retry API call
                        raise ValueError(f"Could not parse JSON after repair:\n{repaired_json}") from e2

                # Basic validation
                for key in ("date", "total", "items"):
                    if key not in data:
                        raise ValueError(f"Missing key `{key}` in parsed data: {data}")

                # Validate items
                if not isinstance(data["items"], list):
                    raise ValueError(f"Items must be a list: {data}")
                for item in data["items"]:
                    if not all(k in item for k in ("description", "amount")):
                        raise ValueError(f"Invalid item structure: {item}")

                logger.info("Successfully parsed and validated JSON")
                return data

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    continue  # Retry on any error
                raise ValueError(f"Failed after {max_retries} attempts: {str(e)}") from e

        raise ValueError(f"Failed to process receipt after {max_retries} attempts")

    def _repair_json(self, invalid_json: str) -> str:
        """
        Attempt to repair invalid JSON by completing arrays and objects.
        Handles cases where the items array is truncated or incomplete.
        """
        try:
            cleaned = invalid_json.strip()
            if not cleaned:
                return '{"date": "", "total": 0, "items": []}'  # Fallback for empty response

            # Ensure JSON starts and ends properly
            if not cleaned.startswith("{"):
                cleaned = "{" + cleaned
            if not cleaned.endswith("}"):
                # Find the last valid item in the items array
                items_end = cleaned.rfind("}")
                if items_end != -1:
                    # Check if last item is incomplete
                    last_comma = cleaned.rfind(",", 0, items_end)
                    last_brace = cleaned.rfind("{", 0, items_end)
                    if last_brace != -1 and last_brace > last_comma:
                        # Truncate incomplete item
                        cleaned = cleaned[:last_brace].rstrip(", \n\t") + "]"
                    else:
                        cleaned = cleaned[:items_end + 1].rstrip(", \n\t") + "]"
                else:
                    cleaned = cleaned.rstrip(", \n\t{") + "]}"

                # Ensure the outer object is closed
                if not cleaned.endswith("}"):
                    cleaned += "}"

            # Remove trailing commas before closing brackets
            cleaned = re.sub(r",\s*(\]|\})", r"\1", cleaned)

            # Validate the repaired JSON
            try:
                json.loads(cleaned)
                return cleaned
            except json.JSONDecodeError:
                logger.warning(f"Repaired JSON still invalid, returning minimal valid JSON")
                return '{"date": "", "total": 0, "items": []}'
        except Exception as e:
            logger.error(f"JSON repair failed: {str(e)}")
            return '{"date": "", "total": 0, "items": []}'  # Fallback to minimal valid JSON