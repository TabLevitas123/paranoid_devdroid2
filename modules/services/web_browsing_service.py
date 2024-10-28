# services/web_browsing_service.py

import logging
import requests
import threading
from typing import Dict, Any, List
from bs4 import BeautifulSoup
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

class WebBrowsingService:
    """
    Manages web browsing activities, including fetching web pages, parsing content,
    handling cookies, and managing browsing sessions securely.
    """

    def __init__(self):
        """
        Initializes the WebBrowsingService with necessary configurations and secure sessions.
        """
        self.logger = setup_logging('WebBrowsingService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.session = requests.Session()
        self.headers = self._load_headers()
        self.lock = threading.Lock()
        self.logger.info("WebBrowsingService initialized successfully.")

    def _load_headers(self) -> Dict[str, str]:
        """
        Loads default headers for web requests from the configuration.
        
        Returns:
            Dict[str, str]: A dictionary of HTTP headers.
        """
        try:
            self.logger.debug("Loading HTTP headers from configuration.")
            headers = {
                'User-Agent': self.config_loader.get('USER_AGENT', 'WebBrowsingService/1.0'),
                'Accept-Language': self.config_loader.get('ACCEPT_LANGUAGE', 'en-US,en;q=0.9'),
                # Add more headers as needed
            }
            self.logger.debug(f"HTTP headers loaded: {headers}")
            return headers
        except Exception as e:
            self.logger.error(f"Error loading HTTP headers: {e}", exc_info=True)
            return {}

    def fetch_page(self, url: str, params: Dict[str, Any] = None, timeout: int = 10) -> str:
        """
        Fetches the content of a web page.
        
        Args:
            url (str): The URL of the web page to fetch.
            params (Dict[str, Any], optional): Query parameters for the request. Defaults to None.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 10.
        
        Returns:
            str: The HTML content of the page.
        """
        try:
            self.logger.debug(f"Fetching page: {url} with params: {params} and timeout: {timeout}")
            with self.lock:
                response = self.session.get(url, headers=self.headers, params=params, timeout=timeout)
            response.raise_for_status()
            self.logger.info(f"Page fetched successfully: {url}")
            return response.text
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching page '{url}': {e}", exc_info=True)
            raise

    def parse_html(self, html_content: str) -> BeautifulSoup:
        """
        Parses HTML content using BeautifulSoup.
        
        Args:
            html_content (str): The HTML content to parse.
        
        Returns:
            BeautifulSoup: The parsed HTML soup.
        """
        try:
            self.logger.debug("Parsing HTML content.")
            soup = BeautifulSoup(html_content, 'html.parser')
            self.logger.debug("HTML content parsed successfully.")
            return soup
        except Exception as e:
            self.logger.error(f"Error parsing HTML content: {e}", exc_info=True)
            raise

    def extract_links(self, soup: BeautifulSoup) -> List[str]:
        """
        Extracts all hyperlinks from the parsed HTML soup.
        
        Args:
            soup (BeautifulSoup): The parsed HTML soup.
        
        Returns:
            List[str]: A list of extracted URLs.
        """
        try:
            self.logger.debug("Extracting links from HTML soup.")
            links = [a.get('href') for a in soup.find_all('a', href=True)]
            self.logger.info(f"Extracted {len(links)} links.")
            return links
        except Exception as e:
            self.logger.error(f"Error extracting links: {e}", exc_info=True)
            return []

    def fetch_and_parse(self, url: str, params: Dict[str, Any] = None, timeout: int = 10) -> BeautifulSoup:
        """
        Fetches a web page and parses its HTML content.
        
        Args:
            url (str): The URL of the web page to fetch.
            params (Dict[str, Any], optional): Query parameters for the request. Defaults to None.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 10.
        
        Returns:
            BeautifulSoup: The parsed HTML soup.
        """
        try:
            self.logger.debug(f"Fetching and parsing page: {url}")
            html_content = self.fetch_page(url, params, timeout)
            soup = self.parse_html(html_content)
            self.logger.info(f"Page fetched and parsed successfully: {url}")
            return soup
        except Exception as e:
            self.logger.error(f"Error fetching and parsing page '{url}': {e}", exc_info=True)
            raise

    def login(self, login_url: str, credentials: Dict[str, str], timeout: int = 10) -> bool:
        """
        Performs a login action on a website by submitting credentials.
        
        Args:
            login_url (str): The URL of the login endpoint.
            credentials (Dict[str, str]): A dictionary containing login credentials (e.g., username, password).
            timeout (int, optional): Timeout for the request in seconds. Defaults to 10.
        
        Returns:
            bool: True if login is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Attempting to login at {login_url} with credentials {credentials}")
            with self.lock:
                response = self.session.post(login_url, data=credentials, headers=self.headers, timeout=timeout)
            response.raise_for_status()
            if self._is_logged_in(response.text):
                self.logger.info("Login successful.")
                return True
            else:
                self.logger.warning("Login failed: Incorrect credentials or additional verification required.")
                return False
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error during login at '{login_url}': {e}", exc_info=True)
            return False

    def _is_logged_in(self, html_content: str) -> bool:
        """
        Determines if the login was successful by analyzing the HTML content.
        
        Args:
            html_content (str): The HTML content returned after login.
        
        Returns:
            bool: True if logged in, False otherwise.
        """
        try:
            self.logger.debug("Checking if login was successful.")
            soup = self.parse_html(html_content)
            # Example check: presence of a logout button or user profile
            if soup.find('a', href='/logout') or soup.find('div', class_='user-profile'):
                self.logger.debug("Login detected based on HTML content.")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error determining login status: {e}", exc_info=True)
            return False

    def perform_search(self, search_url: str, query: str, params: Dict[str, Any] = None, timeout: int = 10) -> BeautifulSoup:
        """
        Performs a search on a website and returns the parsed results.
        
        Args:
            search_url (str): The URL of the search endpoint.
            query (str): The search query.
            params (Dict[str, Any], optional): Additional query parameters. Defaults to None.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 10.
        
        Returns:
            BeautifulSoup: The parsed HTML soup of the search results.
        """
        try:
            self.logger.debug(f"Performing search on {search_url} with query '{query}' and params {params}")
            search_params = {'q': query}
            if params:
                search_params.update(params)
            soup = self.fetch_and_parse(search_url, search_params, timeout)
            self.logger.info(f"Search performed successfully for query '{query}'.")
            return soup
        except Exception as e:
            self.logger.error(f"Error performing search on '{search_url}': {e}", exc_info=True)
            raise

    def download_file(self, file_url: str, destination_path: str, timeout: int = 30) -> bool:
        """
        Downloads a file from the specified URL to the destination path.
        
        Args:
            file_url (str): The URL of the file to download.
            destination_path (str): The local path where the file will be saved.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 30.
        
        Returns:
            bool: True if the download is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Downloading file from {file_url} to {destination_path} with timeout {timeout}")
            with self.lock:
                response = self.session.get(file_url, headers=self.headers, timeout=timeout, stream=True)
            response.raise_for_status()
            with open(destination_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            self.logger.info(f"File downloaded successfully from {file_url} to {destination_path}.")
            return True
        except Exception as e:
            self.logger.error(f"Error downloading file from '{file_url}': {e}", exc_info=True)
            return False

    def close_session(self):
        """
        Closes the current browsing session.
        """
        try:
            self.logger.debug("Closing browsing session.")
            self.session.close()
            self.logger.info("Browsing session closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing browsing session: {e}", exc_info=True)
            raise
