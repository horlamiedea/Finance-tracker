import logging
import traceback
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup

from .models import ParserFunction

logger = logging.getLogger(__name__)

class HTMLParserService:
    """
    A dynamic, rule-based parser that executes AI-generated Python functions
    stored in the database to extract transaction details from email HTML.
    """

    def get_bank_name_from_html(self, email_html: str) -> str:
        """
        A more robust method to identify the bank from email content.
        It uses a prioritized search to avoid misidentification.
        """
        soup = BeautifulSoup(email_html, 'html.parser')
        
        # Create a map of keywords to bank names for easy extension
        bank_keywords = {
            'Providus Bank': ['providusbank', 'providus bank'],
            'OPay': ['opay'],
            'Moniepoint': ['moniepoint'],
            'UBA': ['united bank for africa', 'uba'],
            'GTBank': ['guaranty trust bank', 'gtbank', 'gtb'],
            'Zenith Bank': ['zenith bank'],
            'Access Bank': ['access bank'],
            'First Bank': ['first bank', 'firstbank'],
            'Kuda Bank': ['kuda'],
        }

        # Priority 1: Check for prominent text in headers or strong tags
        for tag_name in ['h1', 'h2', 'strong', 'b']:
            for tag in soup.find_all(tag_name):
                tag_text = tag.get_text().lower()
                for bank_name, keywords in bank_keywords.items():
                    if any(keyword in tag_text for keyword in keywords):
                        logger.info(f"Identified bank as '{bank_name}' from prominent tag <{tag_name}>.")
                        return bank_name

        # Priority 2: Fallback to searching the entire text body
        email_text = soup.get_text().lower()
        for bank_name, keywords in bank_keywords.items():
            if any(keyword in email_text for keyword in keywords):
                logger.info(f"Identified bank as '{bank_name}' from general text search.")
                return bank_name
        
        logger.warning("Could not identify bank from email content.")
        return 'Unknown'

    def run_single_parser(self, parser_code: str, email_html: str) -> Optional[Dict[str, Any]]:
        """
        Safely executes a single string of parser code.
        """
        try:
            soup = BeautifulSoup(email_html, 'html.parser')
            
            local_scope = {
                'soup': soup, 
                're': __import__('re'), 
                'date_parser': __import__('dateutil.parser')
            }
            exec_scope = {}

            exec(parser_code, local_scope, exec_scope)
            
            parser_function = exec_scope.get('parse_email')
            
            if callable(parser_function):
                parsed_data = parser_function(soup)
                if parsed_data and isinstance(parsed_data, dict) and parsed_data.get('amount'):
                    return parsed_data
        except Exception as e:
            error_trace = traceback.format_exc()
            logger.error(f"Execution of generated parser failed: {e}\nTrace: {error_trace}\nCode that failed:\n{parser_code}")
        
        return None

    def run_all_parsers(self, email_html: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves all saved parser functions from the database and tries each one
        until a successful extraction occurs.
        """
        parsers = ParserFunction.objects.all()
        if not parsers:
            return None
            
        logger.info(f"Attempting to parse email with {len(parsers)} saved HTML parsers...")
        
        for parser in parsers:
            parsed_data = self.run_single_parser(parser.parser_code, email_html)
            if parsed_data:
                logger.info(f"Successfully parsed email with saved parser for '{parser.bank_name}'.")
                parsed_data['bank_name'] = parser.bank_name
                return parsed_data
        
        logger.warning("None of the saved HTML parsers were successful.")
        return None
