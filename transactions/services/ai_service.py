import os
import json
import logging
from typing import Optional, Dict, Any

from bs4 import BeautifulSoup
from openai import OpenAI, APIError
from google.generativeai import GenerativeModel, configure as configure_google_ai
from google.api_core.exceptions import GoogleAPIError
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# --- AI Configuration ---
# It's best practice to configure clients once.
try:
    OPENAI_CLIENT = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    OPENAI_CLIENT = None
    logger.error(f"Failed to initialize OpenAI client: {e}")

try:
    configure_google_ai(api_key=os.getenv("GOOGLE_API_KEY"))
    GEMINI_CLIENT = GenerativeModel("gemini-2.5-flash-latest")
except Exception as e:
    GEMINI_CLIENT = None
    logger.error(f"Failed to initialize Google Gemini client: {e}")


class AIService:
    """
    A resilient AI service for parsing and categorizing transactions.
    It attempts to use a primary AI provider (OpenAI) and falls back
    to a secondary provider (Google Gemini) on failure.
    """

    def _get_extraction_prompt(self) -> str:
        return """You are an expert financial data extraction API. You will be given the text content of a bank transaction email.
    Your task is to extract the following details and return them as a SINGLE, VALID JSON object.
    Do not include any text, markdown, or formatting before or after the JSON object.

    **CRITICAL RULES for Transaction Type:**
    - A 'debit' means money is LEAVING the account. Keywords: Debit Alert, Transfer to, Payment to, sent, purchase, withdrawal.
    - A 'credit' means money is ENTERING the account. Keywords: Credit Alert, Received from, deposit, payment received.

    The required JSON keys are:
    - "transaction_type": Must be either "debit" or "credit".
    - "amount": The transaction amount as a string (e.g., "300250.00").
    - "currency": The currency code (e.g., "NGN", "USD"). Default to "NGN" if not specified.
    - "date": The date of the transaction in any parseable format (e.g., "YYYY-MM-DD HH:MM:SS" or "Fri, Jun 27, 2025 at 9:10 PM").
    - "narration": The actual transaction narration, narrative, or description ONLY. Do NOT include the entire email, greetings, disclaimers, or unrelated details. If there is a field labeled "Narration", "Narrative", or "Description", extract ONLY its value. If not, extract the briefest phrase that describes the transaction (e.g., "POS PURCHASE AT SHOPRITE" or "Transfer to John Doe").
    - "bank_name": The name of the bank (e.g., "Providus Bank", "Moniepoint"). Note: This may be overridden by email metadata.
    - "account_balance": The available account balance after the transaction, as a string. Use null if not available.

    If you cannot find a specific piece of information, set its value to null.
    If the email is not a transaction alert, return a JSON object with "transaction_type" set to null.
    """

    def _parse_with_openai(self, text_content: str) -> Optional[Dict[str, Any]]:
        """Attempts to parse transaction data using OpenAI's GPT-4o mini."""
        if not OPENAI_CLIENT:
            logger.warning("OpenAI client not available.")
            return None
            
        logger.info("Attempting to parse with OpenAI GPT-4o mini...")
        try:
            response = OPENAI_CLIENT.chat.completions.create(
                model="gpt-4o-mini",
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
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred with OpenAI client: {e}")
            raise

    def _parse_with_gemini(self, text_content: str) -> Optional[Dict[str, Any]]:
        """Attempts to parse transaction data using Google's Gemini as a fallback."""
        if not GEMINI_CLIENT:
            logger.warning("Google Gemini client not available.")
            return None

        logger.info("Fallback: Attempting to parse with Google Gemini...")
        try:
            full_prompt = self._get_extraction_prompt() + "\n\nEmail Content:\n" + text_content
            response = GEMINI_CLIENT.generate_content(full_prompt)
            
            cleaned_response = response.text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned_response)
        except (GoogleAPIError, ValueError) as e:
            logger.error(f"Google Gemini API error or JSON parsing failed: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred with Gemini client: {e}")
            return None


    def extract_transaction_from_email(self, email_body: str) -> Optional[Dict[str, Any]]:
        """
        Parses raw email text to extract transaction details using a primary AI
        with a fallback to a secondary AI.
        """
        soup = BeautifulSoup(email_body, 'html.parser')
        clean_text = ' '.join(soup.stripped_strings)
        clean_text = ' '.join(clean_text.split())

        if len(clean_text) < 40:
            logger.info("Skipping email processing: content too short.")
            return None

        try:
            parsed_data = self._parse_with_openai(clean_text)
        except Exception:
            parsed_data = self._parse_with_gemini(clean_text)

    
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

    def _categorize_with_openai(self, narration: str, categories: List[str], examples: List[Dict]) -> Optional[str]:
        """Internal method to categorize using OpenAI."""
        if not OPENAI_CLIENT:
            logger.warning("OpenAI client not available for categorization.")
            return None
        
        prompt = self._get_categorization_prompt(narration, categories, examples)
        try:
            response = OPENAI_CLIENT.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=25  # Increased slightly for longer category names
            )
            category = response.choices[0].message.content.strip().strip('"')
            # Validate if the returned category is in the provided list
            if category in categories:
                return category
            return "Unknown" # Default if AI hallucinates a new category
        except APIError as e:
            logger.error(f"OpenAI API error during categorization: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected OpenAI error during categorization: {e}")
            raise

    def _categorize_with_gemini(self, narration: str, categories: List[str], examples: List[Dict]) -> Optional[str]:
        """Internal method to categorize using Gemini."""
        if not GEMINI_CLIENT:
            logger.warning("Google Gemini client not available for categorization.")
            return None
            
        prompt = self._get_categorization_prompt(narration, categories, examples)
        try:
            response = GEMINI_CLIENT.generate_content(prompt)
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
        Categorizes a transaction using a primary AI with a fallback.
        
        Args:
            narration: The narration of the transaction to categorize.
            categories: A list of possible category names.
            examples: A list of dicts, with {"narration": str, "category__name": str}, for few-shot prompting.
            
        Returns:
            The name of the best-fit category, or "Unknown".
        """
        try:
            category = self._categorize_with_openai(narration, categories, examples)
        except Exception:
            category = self._categorize_with_gemini(narration, categories, examples)
            
        return category or "Unknown"
    

    def generate_parser_function(self, email_html: str) -> Optional[str]:
        """
        Uses a powerful AI model to write a Python function that can parse
        the given email HTML.
        """
        # THE FIX: The prompt now enforces defensive coding practices.
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
            logger.info("Attempting to generate parser function with OpenAI...")
            if not OPENAI_CLIENT:
                raise ValueError("OpenAI client not configured.")
            
            response = OPENAI_CLIENT.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            return response.choices[0].message.content.strip().strip('`').strip('python').strip()
        except Exception as e:
            logger.error(f"OpenAI parser generation failed: {e}. Trying fallback.")
            try:
                logger.info("Attempting to generate parser function with Gemini...")
                if not GEMINI_CLIENT:
                    raise ValueError("Gemini client not configured.")
                
                response = GEMINI_CLIENT.generate_content(prompt)
                return response.text.strip().strip('`').strip('python').strip()
            except Exception as e2:
                logger.error(f"Gemini parser generation also failed: {e2}")
                return None
            
    
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
            logger.info("Attempting data recovery with OpenAI...")
            if not OPENAI_CLIENT:
                raise ValueError("OpenAI client not configured.")

            response = OPENAI_CLIENT.chat.completions.create(
                model="gpt-4o-mini", # Mini is sufficient for this focused task
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"AI data recovery failed: {e}")
            return None
