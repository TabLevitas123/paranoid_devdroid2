# services/news_aggregation_service.py

import logging
import threading
import time
from typing import Any, Dict, List, Optional
import requests
from datetime import datetime, timedelta
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

class NewsAggregationServiceError(Exception):
    """Custom exception for NewsAggregationService-related errors."""
    pass

class NewsAggregationService:
    """
    Aggregates news articles from multiple sources using external news APIs.
    Handles fetching, categorizing, filtering, and caching of news data with robust error handling.
    Ensures secure handling of API keys and configurations.
    """

    def __init__(self):
        """
        Initializes the NewsAggregationService with necessary configurations and authentication.
        """
        self.logger = setup_logging('NewsAggregationService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.api_key = self._load_api_key()
        self.base_url = self.config_loader.get('NEWS_API_BASE_URL', 'https://newsapi.org/v2')
        self.cache_duration = self.config_loader.get('NEWS_CACHE_DURATION', 1800)  # in seconds (30 minutes)
        self.cache: Dict[str, Any] = {}
        self.supported_sources = self._load_supported_sources()
        self.supported_categories = self._load_supported_categories()
        self.lock = threading.Lock()
        self.logger.info("NewsAggregationService initialized successfully.")

    def _load_api_key(self) -> str:
        """
        Loads and decrypts the news API key from the configuration.

        Returns:
            str: The decrypted API key.

        Raises:
            NewsAggregationServiceError: If the API key is missing or decryption fails.
        """
        try:
            self.logger.debug("Loading news API key from configuration.")
            encrypted_key = self.config_loader.get('NEWS_API_KEY_ENCRYPTED')
            if not encrypted_key:
                self.logger.error("NEWS_API_KEY_ENCRYPTED not found in configuration.")
                raise NewsAggregationServiceError("NEWS_API_KEY_ENCRYPTED not found in configuration.")
            decrypted_key = self.encryption_manager.decrypt_data(encrypted_key).decode('utf-8')
            self.logger.debug("News API key decrypted successfully.")
            return decrypted_key
        except Exception as e:
            self.logger.error(f"Error loading news API key: {e}", exc_info=True)
            raise NewsAggregationServiceError(f"Error loading news API key: {e}")

    def _load_supported_sources(self) -> List[str]:
        """
        Loads supported news sources from configuration.

        Returns:
            List[str]: A list of supported news source identifiers.
        """
        try:
            self.logger.debug("Loading supported news sources from configuration.")
            sources = self.config_loader.get('SUPPORTED_NEWS_SOURCES', [])
            self.logger.debug(f"Supported news sources loaded: {sources}")
            return sources
        except Exception as e:
            self.logger.error(f"Error loading supported news sources: {e}", exc_info=True)
            return []

    def _load_supported_categories(self) -> List[str]:
        """
        Loads supported news categories from configuration.

        Returns:
            List[str]: A list of supported news categories.
        """
        try:
            self.logger.debug("Loading supported news categories from configuration.")
            categories = self.config_loader.get('SUPPORTED_NEWS_CATEGORIES', [])
            self.logger.debug(f"Supported news categories loaded: {categories}")
            return categories
        except Exception as e:
            self.logger.error(f"Error loading supported news categories: {e}", exc_info=True)
            return []

    def _get_cache_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        """
        Generates a unique cache key based on the endpoint and parameters.

        Args:
            endpoint (str): The API endpoint.
            params (Dict[str, Any]): The query parameters.

        Returns:
            str: The generated cache key.
        """
        import hashlib
        import json

        hash_input = f"{endpoint}_{json.dumps(params, sort_keys=True)}".encode('utf-8')
        cache_key = hashlib.md5(hash_input).hexdigest()
        self.logger.debug(f"Generated cache key: {cache_key} for endpoint: '{endpoint}' with params: {params}")
        return cache_key

    def _is_cache_valid(self, timestamp: float) -> bool:
        """
        Checks if the cached data is still valid based on the cache duration.

        Args:
            timestamp (float): The timestamp when the data was cached.

        Returns:
            bool: True if the cache is valid, False otherwise.
        """
        import time
        current_time = time.time()
        is_valid = (current_time - timestamp) < self.cache_duration
        self.logger.debug(f"Cache validity check: {is_valid} (current_time={current_time}, cached_time={timestamp})")
        return is_valid

    def _fetch_news_data(self, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Fetches news data from the external API with caching.

        Args:
            endpoint (str): The API endpoint.
            params (Dict[str, Any]): The query parameters.

        Returns:
            Optional[Dict[str, Any]]: The news data, or None if fetching fails.
        """
        cache_key = self._get_cache_key(endpoint, params)
        with self.lock:
            if cache_key in self.cache:
                cached_response, timestamp = self.cache[cache_key]
                if self._is_cache_valid(timestamp):
                    self.logger.debug(f"Returning cached data for key '{cache_key}'.")
                    return cached_response
                else:
                    self.logger.debug(f"Cache expired for key '{cache_key}'. Removing from cache.")
                    del self.cache[cache_key]

        url = f"{self.base_url}/{endpoint}"
        params['apiKey'] = self.api_key
        try:
            self.logger.debug(f"Fetching news data from '{url}' with params: {params}")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            with self.lock:
                self.cache[cache_key] = (data, time.time())
            self.logger.info(f"News data fetched successfully from '{url}'.")
            return data
        except requests.exceptions.RequestException as e:
            self.logger.error(f"HTTP request error when fetching news data: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error when fetching news data: {e}", exc_info=True)
            return None

    def get_top_headlines(self, country: str = 'us', category: Optional[str] = None, sources: Optional[List[str]] = None, page_size: int = 20) -> Optional[Dict[str, Any]]:
        """
        Retrieves the top news headlines for a specified country and category.

        Args:
            country (str, optional): The country code (e.g., 'us', 'gb'). Defaults to 'us'.
            category (Optional[str], optional): The news category (e.g., 'business', 'technology'). Defaults to None.
            sources (Optional[List[str]], optional): A list of news sources. Defaults to None.
            page_size (int, optional): The number of articles to retrieve. Defaults to 20.

        Returns:
            Optional[Dict[str, Any]]: The top headlines data, or None if retrieval fails.
        """
        endpoint = 'top-headlines'
        params = {
            'country': country,
            'pageSize': page_size
        }
        if category and category in self.supported_categories:
            params['category'] = category
        if sources and all(source in self.supported_sources for source in sources):
            params['sources'] = ','.join(sources)
        elif sources:
            self.logger.warning("One or more specified sources are not supported.")
        return self._fetch_news_data(endpoint, params)

    def search_news(self, query: str, from_date: Optional[str] = None, to_date: Optional[str] = None, language: Optional[str] = 'en', sort_by: Optional[str] = 'relevancy', page_size: int = 20) -> Optional[Dict[str, Any]]:
        """
        Searches for news articles based on a query.

        Args:
            query (str): The search query.
            from_date (Optional[str], optional): The start date in 'YYYY-MM-DD' format. Defaults to None.
            to_date (Optional[str], optional): The end date in 'YYYY-MM-DD' format. Defaults to None.
            language (Optional[str], optional): The language code. Defaults to 'en'.
            sort_by (Optional[str], optional): The sort order ('relevancy', 'popularity', 'publishedAt'). Defaults to 'relevancy'.
            page_size (int, optional): The number of articles to retrieve. Defaults to 20.

        Returns:
            Optional[Dict[str, Any]]: The search results data, or None if retrieval fails.
        """
        endpoint = 'everything'
        params = {
            'q': query,
            'language': language,
            'sortBy': sort_by,
            'pageSize': page_size
        }
        if from_date:
            params['from'] = from_date
        if to_date:
            params['to'] = to_date
        return self._fetch_news_data(endpoint, params)

    def get_sources(self, category: Optional[str] = None, language: Optional[str] = None, country: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves the list of news sources available.

        Args:
            category (Optional[str], optional): The news category. Defaults to None.
            language (Optional[str], optional): The language code. Defaults to None.
            country (Optional[str], optional): The country code. Defaults to None.

        Returns:
            Optional[Dict[str, Any]]: The sources data, or None if retrieval fails.
        """
        endpoint = 'sources'
        params = {}
        if category and category in self.supported_categories:
            params['category'] = category
        if language:
            params['language'] = language
        if country:
            params['country'] = country
        return self._fetch_news_data(endpoint, params)

    def list_cached_data(self) -> Dict[str, Any]:
        """
        Lists all cached news data.

        Returns:
            Dict[str, Any]: A dictionary of cached data keys and their timestamps.
        """
        try:
            self.logger.debug("Listing all cached news data.")
            cached_keys = {key: value[1] for key, value in self.cache.items()}
            self.logger.info(f"Retrieved {len(cached_keys)} cached news data entries.")
            return cached_keys
        except Exception as e:
            self.logger.error(f"Error listing cached data: {e}", exc_info=True)
            return {}

    def clear_cache_entry(self, endpoint: str, params: Dict[str, Any]) -> bool:
        """
        Clears a specific cache entry based on the endpoint and parameters.

        Args:
            endpoint (str): The API endpoint.
            params (Dict[str, Any]): The query parameters.

        Returns:
            bool: True if the cache entry is cleared successfully, False otherwise.
        """
        try:
            cache_key = self._get_cache_key(endpoint, params)
            with self.lock:
                if cache_key in self.cache:
                    del self.cache[cache_key]
                    self.logger.info(f"Cache entry '{cache_key}' cleared successfully.")
                    return True
                else:
                    self.logger.warning(f"Cache entry '{cache_key}' does not exist.")
                    return False
        except Exception as e:
            self.logger.error(f"Error clearing cache entry '{cache_key}': {e}", exc_info=True)
            return False

    def clear_all_cache(self) -> bool:
        """
        Clears all cached news data.

        Returns:
            bool: True if all cache entries are cleared successfully, False otherwise.
        """
        try:
            self.logger.debug("Clearing all cached news data.")
            with self.lock:
                self.cache.clear()
            self.logger.info("All cached news data cleared successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error clearing all cache: {e}", exc_info=True)
            return False

    def set_cache_duration(self, duration: int) -> bool:
        """
        Sets the duration for which cache entries are considered valid.

        Args:
            duration (int): The cache duration in seconds.

        Returns:
            bool: True if the cache duration is set successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Setting cache duration to {duration} seconds.")
            self.cache_duration = duration
            self.logger.info(f"Cache duration set to {duration} seconds successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error setting cache duration: {e}", exc_info=True)
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing NewsAggregationService resources.")
            # Currently, no persistent resources to close
            self.logger.info("NewsAggregationService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing NewsAggregationService: {e}", exc_info=True)
            raise NewsAggregationServiceError(f"Error closing NewsAggregationService: {e}")
