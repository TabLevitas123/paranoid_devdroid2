# services/api_access_service.py

import logging
import threading
import time
from typing import Any, Dict, Optional, Union
import os
import requests
from requests.adapters import HTTPAdapter, Retry
from urllib.parse import urljoin
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager


class APIAccessServiceError(Exception):
    """Custom exception for APIAccessService-related errors."""
    pass


class APIAccessService:
    """
    Provides API access and integration capabilities, including making HTTP requests,
    handling authentication, managing rate limits, and processing responses. Utilizes the
    requests library with robust error handling and retry mechanisms to ensure reliable
    interactions with external APIs. Ensures secure handling of API keys and sensitive data.
    """

    def __init__(self):
        """
        Initializes the APIAccessService with necessary configurations and authentication.
        """
        self.logger = setup_logging('APIAccessService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.session = self._initialize_session()
        self.logger.info("APIAccessService initialized successfully.")

    def _initialize_session(self) -> requests.Session:
        """
        Initializes a requests session with retry strategy for robust API interactions.

        Returns:
            requests.Session: The configured session object.
        """
        try:
            self.logger.debug("Initializing HTTP session with retry strategy.")
            session = requests.Session()
            retries = Retry(total=5,
                            backoff_factor=0.3,
                            status_forcelist=[500, 502, 503, 504],
                            method_whitelist=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE"])
            adapter = HTTPAdapter(max_retries=retries)
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            self.logger.debug("HTTP session initialized successfully.")
            return session
        except Exception as e:
            self.logger.error(f"Error initializing HTTP session: {e}", exc_info=True)
            raise APIAccessServiceError(f"Error initializing HTTP session: {e}")

    def make_request(self, method: str, url: str, headers: Optional[Dict[str, str]] = None,
                    params: Optional[Dict[str, Any]] = None, data: Optional[Union[Dict[str, Any], str]] = None,
                    json: Optional[Dict[str, Any]] = None, auth: Optional[Any] = None,
                    timeout: int = 30, retries: int = 3) -> Optional[requests.Response]:
        """
        Makes an HTTP request to the specified API endpoint with robust error handling.

        Args:
            method (str): The HTTP method ('GET', 'POST', 'PUT', 'DELETE', etc.).
            url (str): The API endpoint URL.
            headers (Optional[Dict[str, str]], optional): HTTP headers to include in the request. Defaults to None.
            params (Optional[Dict[str, Any]], optional): URL parameters to include in the request. Defaults to None.
            data (Optional[Union[Dict[str, Any], str]], optional): Data to include in the body of the request. Defaults to None.
            json (Optional[Dict[str, Any]], optional): JSON data to include in the body of the request. Defaults to None.
            auth (Optional[Any], optional): Authentication credentials. Defaults to None.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 30.
            retries (int, optional): Number of retry attempts for failed requests. Defaults to 3.

        Returns:
            Optional[requests.Response]: The HTTP response object, or None if the request fails.
        """
        try:
            self.logger.debug(f"Making {method.upper()} request to URL '{url}' with params '{params}' and data '{data}'.")
            with self.lock:
                response = self.session.request(method=method.upper(),
                                                url=url,
                                                headers=headers,
                                                params=params,
                                                data=data,
                                                json=json,
                                                auth=auth,
                                                timeout=timeout)
                response.raise_for_status()
                self.logger.debug(f"Received response with status code {response.status_code}.")
                return response
        except requests.exceptions.HTTPError as http_err:
            self.logger.error(f"HTTP error occurred: {http_err} - Response: {http_err.response.text}", exc_info=True)
            return None
        except requests.exceptions.ConnectionError as conn_err:
            self.logger.error(f"Connection error occurred: {conn_err}", exc_info=True)
            return None
        except requests.exceptions.Timeout as timeout_err:
            self.logger.error(f"Timeout error occurred: {timeout_err}", exc_info=True)
            return None
        except requests.exceptions.RequestException as req_err:
            self.logger.error(f"Request exception occurred: {req_err}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during API request: {e}", exc_info=True)
            return None

    def get(self, url: str, headers: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, Any]] = None, auth: Optional[Any] = None,
            timeout: int = 30, retries: int = 3) -> Optional[requests.Response]:
        """
        Makes a GET request to the specified API endpoint.

        Args:
            url (str): The API endpoint URL.
            headers (Optional[Dict[str, str]], optional): HTTP headers to include in the request. Defaults to None.
            params (Optional[Dict[str, Any]], optional): URL parameters to include in the request. Defaults to None.
            auth (Optional[Any], optional): Authentication credentials. Defaults to None.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 30.
            retries (int, optional): Number of retry attempts for failed requests. Defaults to 3.

        Returns:
            Optional[requests.Response]: The HTTP response object, or None if the request fails.
        """
        return self.make_request('GET', url, headers=headers, params=params, auth=auth, timeout=timeout, retries=retries)

    def post(self, url: str, headers: Optional[Dict[str, str]] = None,
             params: Optional[Dict[str, Any]] = None, data: Optional[Union[Dict[str, Any], str]] = None,
             json: Optional[Dict[str, Any]] = None, auth: Optional[Any] = None,
             timeout: int = 30, retries: int = 3) -> Optional[requests.Response]:
        """
        Makes a POST request to the specified API endpoint.

        Args:
            url (str): The API endpoint URL.
            headers (Optional[Dict[str, str]], optional): HTTP headers to include in the request. Defaults to None.
            params (Optional[Dict[str, Any]], optional): URL parameters to include in the request. Defaults to None.
            data (Optional[Union[Dict[str, Any], str]], optional): Data to include in the body of the request. Defaults to None.
            json (Optional[Dict[str, Any]], optional): JSON data to include in the body of the request. Defaults to None.
            auth (Optional[Any], optional): Authentication credentials. Defaults to None.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 30.
            retries (int, optional): Number of retry attempts for failed requests. Defaults to 3.

        Returns:
            Optional[requests.Response]: The HTTP response object, or None if the request fails.
        """
        return self.make_request('POST', url, headers=headers, params=params, data=data, json=json, auth=auth, timeout=timeout, retries=retries)

    def put(self, url: str, headers: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, Any]] = None, data: Optional[Union[Dict[str, Any], str]] = None,
            json: Optional[Dict[str, Any]] = None, auth: Optional[Any] = None,
            timeout: int = 30, retries: int = 3) -> Optional[requests.Response]:
        """
        Makes a PUT request to the specified API endpoint.

        Args:
            url (str): The API endpoint URL.
            headers (Optional[Dict[str, str]], optional): HTTP headers to include in the request. Defaults to None.
            params (Optional[Dict[str, Any]], optional): URL parameters to include in the request. Defaults to None.
            data (Optional[Union[Dict[str, Any], str]], optional): Data to include in the body of the request. Defaults to None.
            json (Optional[Dict[str, Any]], optional): JSON data to include in the body of the request. Defaults to None.
            auth (Optional[Any], optional): Authentication credentials. Defaults to None.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 30.
            retries (int, optional): Number of retry attempts for failed requests. Defaults to 3.

        Returns:
            Optional[requests.Response]: The HTTP response object, or None if the request fails.
        """
        return self.make_request('PUT', url, headers=headers, params=params, data=data, json=json, auth=auth, timeout=timeout, retries=retries)

    def delete(self, url: str, headers: Optional[Dict[str, str]] = None,
               params: Optional[Dict[str, Any]] = None, auth: Optional[Any] = None,
               timeout: int = 30, retries: int = 3) -> Optional[requests.Response]:
        """
        Makes a DELETE request to the specified API endpoint.

        Args:
            url (str): The API endpoint URL.
            headers (Optional[Dict[str, str]], optional): HTTP headers to include in the request. Defaults to None.
            params (Optional[Dict[str, Any]], optional): URL parameters to include in the request. Defaults to None.
            auth (Optional[Any], optional): Authentication credentials. Defaults to None.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 30.
            retries (int, optional): Number of retry attempts for failed requests. Defaults to 3.

        Returns:
            Optional[requests.Response]: The HTTP response object, or None if the request fails.
        """
        return self.make_request('DELETE', url, headers=headers, params=params, auth=auth, timeout=timeout, retries=retries)

    def handle_rate_limiting(self, response: requests.Response, retries: int = 3, backoff_factor: float = 0.3) -> bool:
        """
        Handles API rate limiting by checking response headers and implementing backoff strategy.

        Args:
            response (requests.Response): The HTTP response object.
            retries (int, optional): Number of retry attempts. Defaults to 3.
            backoff_factor (float, optional): The backoff factor for retries. Defaults to 0.3.

        Returns:
            bool: True if the request should be retried, False otherwise.
        """
        try:
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 1))
                sleep_time = backoff_factor * (2 ** (retries - 1))
                self.logger.warning(f"Rate limit exceeded. Retrying after {retry_after} seconds.")
                time.sleep(retry_after)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error handling rate limiting: {e}", exc_info=True)
            return False

    def authenticate(self, auth_type: str, credentials: Dict[str, Any]) -> Optional[Any]:
        """
        Authenticates with the API using the specified authentication method.

        Args:
            auth_type (str): The type of authentication ('api_key', 'oauth', etc.).
            credentials (Dict[str, Any]): The credentials required for authentication.

        Returns:
            Optional[Any]: The authentication object or token, or None if authentication fails.
        """
        try:
            self.logger.debug(f"Authenticating with auth type '{auth_type}'.")
            if auth_type.lower() == 'api_key':
                api_key = credentials.get('api_key')
                if not api_key:
                    self.logger.error("API key not provided for API key authentication.")
                    return None
                self.logger.debug("API key authentication successful.")
                return {'Authorization': f'Bearer {api_key}'}
            elif auth_type.lower() == 'basic':
                username = credentials.get('username')
                password_encrypted = credentials.get('password')
                if not all([username, password_encrypted]):
                    self.logger.error("Username or password not provided for basic authentication.")
                    return None
                password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
                self.logger.debug("Basic authentication successful.")
                return (username, password)
            elif auth_type.lower() == 'oauth2':
                token_url = credentials.get('token_url')
                client_id = credentials.get('client_id')
                client_secret_encrypted = credentials.get('client_secret')
                scope = credentials.get('scope', '')
                if not all([token_url, client_id, client_secret_encrypted]):
                    self.logger.error("Incomplete credentials for OAuth2 authentication.")
                    return None
                client_secret = self.encryption_manager.decrypt_data(client_secret_encrypted).decode('utf-8')
                data = {
                    'grant_type': 'client_credentials',
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'scope': scope
                }
                response = self.session.post(token_url, data=data)
                if response.status_code == 200:
                    access_token = response.json().get('access_token')
                    self.logger.debug("OAuth2 authentication successful.")
                    return {'Authorization': f'Bearer {access_token}'}
                else:
                    self.logger.error(f"OAuth2 authentication failed with status code {response.status_code}: {response.text}")
                    return None
            else:
                self.logger.error(f"Unsupported authentication type '{auth_type}'.")
                return None
        except Exception as e:
            self.logger.error(f"Error during authentication: {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing APIAccessService resources.")
            self.session.close()
            self.logger.debug("HTTP session closed.")
            self.logger.info("APIAccessService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing APIAccessService: {e}", exc_info=True)
            raise APIAccessServiceError(f"Error closing APIAccessService: {e}")
