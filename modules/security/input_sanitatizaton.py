# security/input_sanitization.py

import logging
import re
from modules.utilities.logging_manager import setup_logging

class InputSanitizationError(Exception):
    """Custom exception for input sanitization failures."""
    pass

class InputSanitizer:
    """
    Provides methods to sanitize and validate user inputs to prevent injection attacks
    and ensure data integrity.
    """

    def __init__(self):
        """
        Initializes the InputSanitizer with necessary configurations.
        """
        self.logger = setup_logging('InputSanitizer')
        self.logger.info("InputSanitizer initialized successfully.")

    def sanitize_string(self, input_string):
        """
        Sanitizes a string input by escaping special characters and removing potentially
        malicious content.

        Args:
            input_string (str): The input string to sanitize.

        Returns:
            str: The sanitized string.
        """
        try:
            self.logger.debug(f"Sanitizing string input: {input_string}")
            # Remove any non-alphanumeric characters except spaces and some punctuation
            sanitized = re.sub(r'[^\w\s\.,!?\'"-]', '', input_string)
            # Optionally, escape HTML characters to prevent XSS
            sanitized = self._escape_html(sanitized)
            self.logger.debug(f"Sanitized string: {sanitized}")
            return sanitized
        except Exception as e:
            self.logger.error(f"Error sanitizing string input: {e}", exc_info=True)
            raise InputSanitizationError(f"Error sanitizing string input: {e}")

    def sanitize_number(self, input_number, min_value=None, max_value=None):
        """
        Sanitizes a numeric input by ensuring it falls within specified bounds.

        Args:
            input_number (int or float): The input number to sanitize.
            min_value (int or float, optional): The minimum allowable value. Defaults to None.
            max_value (int or float, optional): The maximum allowable value. Defaults to None.

        Returns:
            int or float: The sanitized number.

        Raises:
            InputSanitizationError: If the input is not a number or out of bounds.
        """
        try:
            self.logger.debug(f"Sanitizing numeric input: {input_number} with min={min_value}, max={max_value}")
            if not isinstance(input_number, (int, float)):
                raise ValueError("Input is not a number.")
            if min_value is not None and input_number < min_value:
                self.logger.warning(f"Input number {input_number} is less than min value {min_value}. Clamping.")
                input_number = min_value
            if max_value is not None and input_number > max_value:
                self.logger.warning(f"Input number {input_number} is greater than max value {max_value}. Clamping.")
                input_number = max_value
            self.logger.debug(f"Sanitized number: {input_number}")
            return input_number
        except Exception as e:
            self.logger.error(f"Error sanitizing numeric input: {e}", exc_info=True)
            raise InputSanitizationError(f"Error sanitizing numeric input: {e}")

    def sanitize_email(self, email):
        """
        Validates and sanitizes an email address.

        Args:
            email (str): The email address to sanitize.

        Returns:
            str: The sanitized email address.

        Raises:
            InputSanitizationError: If the email is invalid.
        """
        try:
            self.logger.debug(f"Sanitizing email input: {email}")
            email = email.strip()
            email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
            if not re.match(email_regex, email):
                raise ValueError("Invalid email format.")
            sanitized_email = self.sanitize_string(email)
            self.logger.debug(f"Sanitized email: {sanitized_email}")
            return sanitized_email
        except Exception as e:
            self.logger.error(f"Error sanitizing email input: {e}", exc_info=True)
            raise InputSanitizationError(f"Error sanitizing email input: {e}")

    def sanitize_url(self, url):
        """
        Validates and sanitizes a URL.

        Args:
            url (str): The URL to sanitize.

        Returns:
            str: The sanitized URL.

        Raises:
            InputSanitizationError: If the URL is invalid.
        """
        try:
            self.logger.debug(f"Sanitizing URL input: {url}")
            url = url.strip()
            url_regex = re.compile(
                r'^(https?|ftp)://'  # http://, https://, ftp://
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+'  # domain...
                r'(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # ...including TLD
                r'localhost|'  # localhost...
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or IP
                r'(?::\d+)?'  # optional port
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)
            if not re.match(url_regex, url):
                raise ValueError("Invalid URL format.")
            sanitized_url = self._escape_html(url)
            self.logger.debug(f"Sanitized URL: {sanitized_url}")
            return sanitized_url
        except Exception as e:
            self.logger.error(f"Error sanitizing URL input: {e}", exc_info=True)
            raise InputSanitizationError(f"Error sanitizing URL input: {e}")

    def sanitize_filename(self, filename):
        """
        Sanitizes a filename by removing or replacing unsafe characters.

        Args:
            filename (str): The filename to sanitize.

        Returns:
            str: The sanitized filename.

        Raises:
            InputSanitizationError: If the filename is invalid.
        """
        try:
            self.logger.debug(f"Sanitizing filename input: {filename}")
            # Remove any path components and allow only safe characters
            sanitized = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)
            self.logger.debug(f"Sanitized filename: {sanitized}")
            return sanitized
        except Exception as e:
            self.logger.error(f"Error sanitizing filename input: {e}", exc_info=True)
            raise InputSanitizationError(f"Error sanitizing filename input: {e}")

    def sanitize_password(self, password):
        """
        Sanitizes a password input. Typically, passwords are not sanitized to preserve their integrity,
        but you can enforce policies like minimum length, complexity, etc.

        Args:
            password (str): The password to sanitize.

        Returns:
            str: The sanitized password.

        Raises:
            InputSanitizationError: If the password does not meet security policies.
        """
        try:
            self.logger.debug("Sanitizing password input.")
            # Enforce password policies
            if len(password) < 8:
                raise ValueError("Password must be at least 8 characters long.")
            if not re.search(r'[A-Z]', password):
                raise ValueError("Password must contain at least one uppercase letter.")
            if not re.search(r'[a-z]', password):
                raise ValueError("Password must contain at least one lowercase letter.")
            if not re.search(r'\d', password):
                raise ValueError("Password must contain at least one digit.")
            if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
                raise ValueError("Password must contain at least one special character.")
            self.logger.debug("Password meets security policies.")
            return password
        except Exception as e:
            self.logger.error(f"Error sanitizing password input: {e}", exc_info=True)
            raise InputSanitizationError(f"Error sanitizing password input: {e}")

    def sanitize_json(self, json_data):
        """
        Sanitizes JSON input by ensuring keys and values are free from malicious content.

        Args:
            json_data (dict): The JSON data to sanitize.

        Returns:
            dict: The sanitized JSON data.

        Raises:
            InputSanitizationError: If the JSON data is invalid or contains malicious content.
        """
        try:
            self.logger.debug(f"Sanitizing JSON input: {json_data}")
            sanitized_json = {}
            for key, value in json_data.items():
                sanitized_key = self.sanitize_string(key)
                if isinstance(value, str):
                    sanitized_value = self.sanitize_string(value)
                elif isinstance(value, (int, float)):
                    sanitized_value = self.sanitize_number(value)
                elif isinstance(value, dict):
                    sanitized_value = self.sanitize_json(value)
                elif isinstance(value, list):
                    sanitized_value = [self.sanitize_json(item) if isinstance(item, dict) else self.sanitize_string(item) if isinstance(item, str) else item for item in value]
                else:
                    sanitized_value = value  # Leave other data types unchanged
                sanitized_json[sanitized_key] = sanitized_value
            self.logger.debug(f"Sanitized JSON: {sanitized_json}")
            return sanitized_json
        except Exception as e:
            self.logger.error(f"Error sanitizing JSON input: {e}", exc_info=True)
            raise InputSanitizationError(f"Error sanitizing JSON input: {e}")

    def _escape_html(self, text):
        """
        Escapes HTML characters to prevent Cross-Site Scripting (XSS) attacks.

        Args:
            text (str): The text to escape.

        Returns:
            str: The escaped text.
        """
        try:
            self.logger.debug("Escaping HTML characters.")
            html_escape_table = {
                "&": "&amp;",
                '"': "&quot;",
                "'": "&#x27;",
                ">": "&gt;",
                "<": "&lt;",
                "/": "&#x2F;",
            }
            return "".join(html_escape_table.get(c, c) for c in text)
        except Exception as e:
            self.logger.error(f"Error escaping HTML characters: {e}", exc_info=True)
            raise InputSanitizationError(f"Error escaping HTML characters: {e}")
