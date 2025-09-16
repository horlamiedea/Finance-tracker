import os
import json
import logging
import time
from typing import Optional, Dict, Any, List

from bs4 import BeautifulSoup
from google.generativeai import GenerativeModel, configure as configure_google_ai
from google.api_core.exceptions import GoogleAPIError
from openai import OpenAI, APIError

logger = logging.getLogger(__name__)

# --- AI Configuration ---
GEMINI_CLIENTS = []
for i in range(1, 4):
    api_key = os.getenv(f"GOOGLE_API_KEY_{i}")
    if api_key:
        try:
            configure_google_ai(api_key=api_key)
            GEMINI_CLIENTS.append(GenerativeModel("gemini-2.5-pro"))
        except Exception as e:
            logger.error(f"Failed to initialize Google Gemini client for key {i}: {e}")

if not GEMINI_CLIENTS:
    logger.error("No Google Gemini clients were initialized. Please check your GOOGLE_API_KEY environment variables.")

try:
    OPENAI_CLIENT = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    OPENAI_CLIENT = None
    logger.error(f"Failed to initialize OpenAI client: {e}")


class AIService:
    """
    An AI service for parsing and categorizing transactions using Google Gemini,
    with a fallback to OpenAI's GPT-4o.
    """
    def __init__(self):
        self.gemini_client_index = 0

    def _get_extraction_prompt(self) -> str:
        return """
You are an expert financial data extraction API. You will be given the text content of a bank transaction email.
Your task is to extract the following details and return them as a SINGLE, VALID JSON object.
Do not include any text, markdown, or formatting before or after the JSON object.

**CRITICAL RULES for Transaction Type:**
- A 'debit' means money is LEAVING the account. Keywords: Debit Alert, Transfer to, Payment to, sent, purchase, withdrawal, bill payment. If the email says "you sent" or "you spent", it is a debit.
- A 'credit' means money is ENTERING the account. Keywords: Credit Alert, Received from, Transfer from, deposit, payment received. If the email says "you received", it is a credit.
- If the subject is "Transaction Notification" or similar, you MUST examine the email body to determine if it is a debit or credit.

The required JSON keys are:
- "transaction_type": Must be either "debit" or "credit".
- "amount": The transaction amount as a string (e.g., "300250.00").
- "currency": The currency code (e.g., "NGN", "USD"). Default to "NGN" if not specified.
- "date": The date of the transaction in any parseable format (e.g., "YYYY-MM-DD HH:MM:SS" or "Fri, Jun 27, 2025 at 9:10 PM").
- "narration": The actual transaction narration. This should be cleaned of any transactional codes, reference numbers, or other machine-readable identifiers. For example:
    - "BILL PAYMENT - FUNDS TRANSFER POS@<2ISAIUFX> <2302BA000009611> <229260035188@2ISAH9HFPAYCLIQ LIMITED  NG> <229260035188> <100562/877787>" should become "BILL PAYMENT - FUNDS TRANSFER POS 2ISAH9HFPAYCLIQ LIMITED NG".
    - "AIRTIME TO 08160226835 MTN/ATP|2MPT99l1w|1966744399411990528" should become "AIRTIME TO 08160226835".
    - "BILL PAYMENT FOR LOOKMAN AYINDE KAREEM Ikeja Electricity Distribution Prepaid 0213240200799/BPT|2MPT99l1w|1966744085187317760" should become "BILL PAYMENT FOR LOOKMAN AYINDE KAREEM Ikeja Electricity Distribution Prepaid".
    - "TRANSFER TO Atreos Retail Platform Limited - Bokku Mart Grammar Sch Ojodu Moniepoint MFB *****96254/TRF|2MPT99l1w|1966587778479702016" should become "TRANSFER TO Atreos Retail Platform Limited - Bokku Mart Grammar Sch Ojodu Moniepoint MFB".
    - "CASH WITHDRAWAL FROM OTHERS ATM ATM@<10322851> <000000000000000> <CAID00110322851         LAGOS         NG> <002765324844> <465679/421544>" should become "CASH WITHDRAWAL FROM OTHERS ATM".
    - "ATM WITHDRAWAL COMMISSION ATM@<10322851> <000000000000000> <CAID00110322851         LAGOS         NG> <002765324844> <465679/421544>" should become "ATM WITHDRAWAL COMMISSION".
- "bank_name": The name of the bank (e.g., "Providus Bank", "Moniepoint"). Note: This may be overridden by email metadata.
- "account_balance": The available account balance after the transaction, as a string. Use null if not available.

If you cannot find a specific piece of information, set its value to null.
If the email is not a transaction alert, return a JSON object with "transaction_type" set to null.
"""

    def _parse_with_gemini(self, text_content: str, attempt: int = 1) -> Optional[Dict[str, Any]]:
        """Attempts to parse transaction data using Google's Gemini."""
        if not GEMINI_CLIENTS:
            logger.warning("No Google Gemini clients available.")
            return None

        client = GEMINI_CLIENTS[self.gemini_client_index]
        logger.info(f"Attempting to parse with Google Gemini (Key {self.gemini_client_index + 1}, Attempt {attempt})...")
        try:
            full_prompt = self._get_extraction_prompt() + "\n\nEmail Content:\n" + text_content
            response = client.generate_content(full_prompt)
            
            cleaned_response = response.text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned_response)
        except GoogleAPIError as e:
            if "429" in str(e):
                logger.warning(f"Gemini API rate limit hit for key {self.gemini_client_index + 1}. Rotating to next key.")
                self.gemini_client_index = (self.gemini_client_index + 1) % len(GEMINI_CLIENTS)
                return None
            logger.error(f"Google Gemini API error for key {self.gemini_client_index + 1}: {e}")
            self.gemini_client_index = (self.gemini_client_index + 1) % len(GEMINI_CLIENTS)
            return None
        except ValueError as e:
            logger.error(f"JSON parsing failed: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred with Gemini client: {e}")
            return None

    def _parse_with_openai(self, text_content: str) -> Optional[Dict[str, Any]]:
        """Attempts to parse transaction data using OpenAI's GPT-4o as a fallback."""
        if not OPENAI_CLIENT:
            logger.warning("OpenAI client not available.")
            return None
            
        logger.info("Fallback: Attempting to parse with OpenAI GPT-4o...")
        try:
            response = OPENAI_CLIENT.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": self._get_extraction_prompt()},
                    {"role": "user", "content": text_content}
                ],
                temperature=0.0,
            )
            return json.loads(response.choices[0].message.content)
        except APIError as e:
            logger.error(f"OpenAI API error: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred with OpenAI client: {e}")
            return None

    def extract_transaction_from_email(self, email_body: str) -> Optional[Dict[str, Any]]:
        """
        Parses raw email text to extract transaction details using Google Gemini,
        with a fallback to OpenAI's GPT-4o after 5 failed attempts.
        """
        soup = BeautifulSoup(email_body, 'html.parser')
        clean_text = ' '.join(soup.stripped_strings)
        clean_text = ' '.join(clean_text.split())

        if len(clean_text) < 40:
            logger.info("Skipping email processing: content too short.")
            return None
        
        for i in range(len(GEMINI_CLIENTS) * 2): # Try each key twice
            parsed_data = self._parse_with_gemini(clean_text, attempt=i + 1)
            if parsed_data:
                return parsed_data
            time.sleep(5)

        return self._parse_with_openai(clean_text)

    def _get_categorization_prompt(self, narration: str, categories: List[str], examples: List[Dict]) -> str:
        """Generates a few-shot prompt for accurate categorization."""
        
        example_str = "\n".join([f"- Narration: \"{ex['narration']}\" -> Category: \"{ex['category__name']}\"" for ex in examples])

        return f"""
You are an expert financial transaction categorizer. Your goal is to assign the most relevant category to a new transaction based on its narration and examples of past categorizations.

**Available Categories:**
{', '.join(categories)}

**Examples of Previously Categorized Transactions:**
{example_str if example_str else "No examples available."}

**New Transaction to Categorize:**
- Narration: "{narration}"

Based on the narration and the examples provided, which of the "Available Categories" is the best fit?
Respond ONLY with the name of the category from the list. If no category is a good fit, respond with "Unknown".
"""

    def _categorize_with_gemini(self, narration: str, categories: List[str], examples: List[Dict]) -> Optional[str]:
        """Internal method to categorize using Gemini."""
        if not GEMINI_CLIENTS:
            logger.warning("No Google Gemini clients available for categorization.")
            return None
            
        client = GEMINI_CLIENTS[self.gemini_client_index]
        prompt = self._get_categorization_prompt(narration, categories, examples)
        try:
            response = client.generate_content(prompt)
            category = response.text.strip().strip('"')
            if category in categories:
                return category
            return "Unknown"
        except (GoogleAPIError, ValueError) as e:
            logger.error(f"Google Gemini API error during categorization: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected Gemini error during categorization: {e}")
            return None

    def categorize_transaction(self, narration: str, categories: List[str], examples: List[Dict]) -> str:
        """
        Categorizes a transaction using Google Gemini.
        
        Args:
            narration: The narration of the transaction to categorize.
            categories: A list of possible category names.
            examples: A list of dicts, with {"narration": str, "category__name": str}, for few-shot prompting.
            
        Returns:
            The name of the best-fit category, or "Unknown".
        """
        category = self._categorize_with_gemini(narration, categories, examples)
        return category or "Unknown"

    def recover_missing_data_from_text(self, text_block: str) -> Optional[Dict[str, Any]]:
        """
        Takes a jumbled block of text from a failed parse and attempts
        to recover the essential transaction details from it.
        """
        if not text_block:
            return None

        prompt = f"""
You are a data recovery specialist. You will be given a block of messy text extracted from a financial email. Your task is to find and extract the following specific details from this text.

**CRITICAL RULES for Transaction Type:**
- A 'debit' means money is LEAVING the account. Keywords: Debit transaction, OUTWARD TRANSFER.
- A 'credit' means money is ENTERING the account. Keywords: Credit transaction, INWARD TRANSFER.

**Data to Extract:**
1.  `transaction_type`: "debit" or "credit".
2.  `date`: The full date and time of the transaction.
3.  `narration`: The transaction description or narrative.
4.  `amount`: The numerical amount of the transaction.
5.  `account_balance`: The available balance after the transaction.

Here is the messy text block:
---
{text_block}
---

Respond ONLY with a valid JSON object containing the keys you were able to find. If a key cannot be found, its value should be null.
"""
        try:
            logger.info("Attempting data recovery with Gemini...")
            if not GEMINI_CLIENTS:
                raise ValueError("Gemini client not configured.")
            
            client = GEMINI_CLIENTS[self.gemini_client_index]
            response = client.generate_content(prompt)
            cleaned_response = response.text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned_response)
        except GoogleAPIError as e:
            if "429" in str(e):
                logger.warning("Gemini API rate limit hit during data recovery. Waiting 60 seconds before retrying...")
                time.sleep(60)
                return self.recover_missing_data_from_text(text_block)
            logger.error(f"Google Gemini API error during data recovery: {e}")
            return None
        except ValueError as e:
            logger.error(f"JSON parsing failed during data recovery: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred with Gemini client during data recovery: {e}")
            return None

    def extract_data_from_receipt(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Extracts transaction data from a receipt file (image or PDF) using Gemini.
        """
        if not GEMINI_CLIENTS:
            logger.warning("No Google Gemini clients available for receipt processing.")
            return None

        client = GEMINI_CLIENTS[self.gemini_client_index]
        logger.info(f"Attempting to extract data from receipt with Google Gemini (Key {self.gemini_client_index + 1})...")

        try:
            with open(file_path, "rb") as f:
                image_data = f.read()

            prompt = """
You are an expert receipt data extraction API. You will be given an image or PDF of a receipt.
Your task is to extract the following details and return them as a SINGLE, VALID JSON object.
Do not include any text, markdown, or formatting before or after the JSON object.

The required JSON keys are:
- "total": The total amount of the transaction as a string (e.g., "300250.00").
- "date": The date of the transaction in "YYYY-MM-DD" format.
- "items": A list of items, where each item is a dictionary with "description" and "amount" keys.

If you cannot find a specific piece of information, set its value to null.
"""
            
            response = client.generate_content([prompt, {"mime_type": "image/jpeg", "data": image_data}])
            cleaned_response = response.text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned_response)
        except GoogleAPIError as e:
            if "429" in str(e):
                logger.warning(f"Gemini API rate limit hit for key {self.gemini_client_index + 1}. Rotating to next key.")
                self.gemini_client_index = (self.gemini_client_index + 1) % len(GEMINI_CLIENTS)
                return self.extract_data_from_receipt(file_path)
            logger.error(f"Google Gemini API error: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred during receipt processing: {e}")
            return None

    def generate_parser_function(self, email_html: str) -> Optional[str]:
        """
        Uses Gemini to write a Python function that can parse the given email HTML.
        """
        prompt = f"""
You are an expert Python programmer specializing in web scraping with BeautifulSoup.
Your task is to write a single Python function named `parse_email` that takes a BeautifulSoup `soup` object as input.
This function must parse the provided HTML to extract financial transaction details.

**EXECUTION CONTEXT:**
Your function will be executed in a restricted scope where only the following modules are available:
- `soup`: The BeautifulSoup object of the email HTML.
- `re`: The Python regex module.
- `date_parser`: The `dateutil.parser` module.

**FUNCTION REQUIREMENTS:**
- The function signature MUST be `def parse_email(soup):`.
- The function MUST return a Python dictionary with these exact keys: "transaction_type", "amount", "date", "narration", "account_balance".
- All values in the returned dictionary must be STRINGS, or `None` if a value cannot be found.

**DEFENSIVE CODING PRACTICES (VERY IMPORTANT):**
- When extracting text, if your selector might fail, handle the `None` case.
- Inside every helper function you write (e.g., `extract_amount`), you MUST check if the input `text` is `None`. If it is, return `None` immediately to prevent `TypeError`. For example: `if not text: return None`. This is the most common source of errors.

Here is the HTML to parse:
```html
{email_html}
```

Respond ONLY with the complete, raw Python code for the function. Do not add comments, explanations, or example usage.
"""
        try:
            logger.info("Attempting to generate parser function with Gemini...")
            if not GEMINI_CLIENTS:
                raise ValueError("Gemini client not configured.")
            
            client = GEMINI_CLIENTS[self.gemini_client_index]
            response = client.generate_content(prompt)
            return response.text.strip().strip('`').strip('python').strip()
        except Exception as e:
            logger.error(f"Gemini parser generation failed: {e}")
            return None
