# services/stock_market_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
import requests
import time
import hashlib
import json
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

class StockMarketServiceError(Exception):
    """Custom exception for StockMarketService-related errors."""
    pass

class StockMarketService:
    """
    Provides stock market data retrieval capabilities by interfacing with external stock market APIs.
    Handles fetching current prices, historical data, real-time quotes, and performs basic analysis
    with robust error handling and caching mechanisms. Ensures secure handling of API keys and configurations.
    """

    def __init__(self):
        """
        Initializes the StockMarketService with necessary configurations and authentication.
        """
        self.logger = setup_logging('StockMarketService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.api_key = self._load_api_key()
        self.base_url = self.config_loader.get('STOCK_API_BASE_URL', 'https://www.alphavantage.co/query')
        self.cache_duration = self.config_loader.get('STOCK_CACHE_DURATION', 300)  # in seconds (5 minutes)
        self.cache: Dict[str, Any] = {}
        self.lock = threading.Lock()
        self.logger.info("StockMarketService initialized successfully.")

    def _load_api_key(self) -> str:
        """
        Loads and decrypts the stock API key from the configuration.

        Returns:
            str: The decrypted API key.

        Raises:
            StockMarketServiceError: If the API key is missing or decryption fails.
        """
        try:
            self.logger.debug("Loading stock API key from configuration.")
            encrypted_key = self.config_loader.get('STOCK_API_KEY_ENCRYPTED')
            if not encrypted_key:
                self.logger.error("STOCK_API_KEY_ENCRYPTED not found in configuration.")
                raise StockMarketServiceError("STOCK_API_KEY_ENCRYPTED not found in configuration.")
            decrypted_key = self.encryption_manager.decrypt_data(encrypted_key).decode('utf-8')
            self.logger.debug("Stock API key decrypted successfully.")
            return decrypted_key
        except Exception as e:
            self.logger.error(f"Error loading stock API key: {e}", exc_info=True)
            raise StockMarketServiceError(f"Error loading stock API key: {e}")

    def _get_cache_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        """
        Generates a unique cache key based on the endpoint and parameters.

        Args:
            endpoint (str): The API endpoint.
            params (Dict[str, Any]): The query parameters.

        Returns:
            str: The generated cache key.
        """
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
        current_time = time.time()
        is_valid = (current_time - timestamp) < self.cache_duration
        self.logger.debug(f"Cache validity check: {is_valid} (current_time={current_time}, cached_time={timestamp})")
        return is_valid

    def _fetch_stock_data(self, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Fetches stock data from the external API with caching.

        Args:
            endpoint (str): The API endpoint.
            params (Dict[str, Any]): The query parameters.

        Returns:
            Optional[Dict[str, Any]]: The stock data, or None if fetching fails.
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

        try:
            self.logger.debug(f"Fetching stock data from '{self.base_url}' with params: {params}")
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            with self.lock:
                self.cache[cache_key] = (data, time.time())
            self.logger.info(f"Stock data fetched successfully from '{self.base_url}'.")
            return data
        except requests.exceptions.RequestException as e:
            self.logger.error(f"HTTP request error when fetching stock data: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error when fetching stock data: {e}", exc_info=True)
            return None

    def get_current_price(self, symbol: str, market: Optional[str] = 'GLOBAL') -> Optional[Dict[str, Any]]:
        """
        Retrieves the current price of a specified stock symbol.

        Args:
            symbol (str): The stock symbol (e.g., 'AAPL', 'GOOGL').
            market (Optional[str], optional): The market identifier. Defaults to 'GLOBAL'.

        Returns:
            Optional[Dict[str, Any]]: The current price data, or None if retrieval fails.
        """
        endpoint = 'GLOBAL_QUOTE'
        params = {'function': endpoint, 'symbol': symbol, 'apikey': self.api_key}
        return self._fetch_stock_data(endpoint, params)

    def get_historical_data(self, symbol: str, interval: str = 'Daily', outputsize: str = 'compact') -> Optional[Dict[str, Any]]:
        """
        Retrieves historical stock data for a specified symbol.

        Args:
            symbol (str): The stock symbol.
            interval (str, optional): The interval between data points ('Daily', 'Weekly', 'Monthly'). Defaults to 'Daily'.
            outputsize (str, optional): The amount of data to retrieve ('compact', 'full'). Defaults to 'compact'.

        Returns:
            Optional[Dict[str, Any]]: The historical data, or None if retrieval fails.
        """
        endpoint = 'TIME_SERIES_DAILY_ADJUSTED'
        params = {'function': endpoint, 'symbol': symbol, 'outputsize': outputsize, 'apikey': self.api_key}
        return self._fetch_stock_data(endpoint, params)

    def get_real_time_quotes(self, symbols: List[str]) -> Optional[Dict[str, Any]]:
        """
        Retrieves real-time stock quotes for a list of symbols.

        Args:
            symbols (List[str]): A list of stock symbols.

        Returns:
            Optional[Dict[str, Any]]: The real-time quotes data, or None if retrieval fails.
        """
        endpoint = 'BATCH_STOCK_QUOTES'
        params = {'function': endpoint, 'symbols': ','.join(symbols), 'apikey': self.api_key}
        return self._fetch_stock_data(endpoint, params)

    def analyze_trend(self, symbol: str, period: int = 30) -> Optional[Dict[str, Any]]:
        """
        Analyzes the stock price trend over a specified period.

        Args:
            symbol (str): The stock symbol.
            period (int, optional): The number of days to analyze. Defaults to 30.

        Returns:
            Optional[Dict[str, Any]]: The trend analysis data, or None if analysis fails.
        """
        historical_data = self.get_historical_data(symbol, outputsize='full')
        if not historical_data:
            self.logger.error(f"Failed to retrieve historical data for symbol '{symbol}'.")
            return None

        try:
            time_series = historical_data.get('Time Series (Daily)', {})
            sorted_dates = sorted(time_series.keys(), reverse=True)
            recent_dates = sorted_dates[:period]
            closing_prices = [float(time_series[date]['4. close']) for date in recent_dates]
            average_price = sum(closing_prices) / len(closing_prices)
            trend = 'upward' if closing_prices[0] > closing_prices[-1] else 'downward' if closing_prices[0] < closing_prices[-1] else 'stable'
            analysis = {
                'symbol': symbol,
                'period': period,
                'average_closing_price': average_price,
                'trend': trend
            }
            self.logger.info(f"Trend analysis for '{symbol}': {analysis}")
            return analysis
        except Exception as e:
            self.logger.error(f"Error analyzing trend for symbol '{symbol}': {e}", exc_info=True)
            return None

    def list_cached_data(self) -> Dict[str, Any]:
        """
        Lists all cached stock data.

        Returns:
            Dict[str, Any]: A dictionary of cached data keys and their timestamps.
        """
        try:
            self.logger.debug("Listing all cached stock data.")
            cached_keys = {key: value[1] for key, value in self.cache.items()}
            self.logger.info(f"Retrieved {len(cached_keys)} cached stock data entries.")
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
        Clears all cached stock data.

        Returns:
            bool: True if all cache entries are cleared successfully, False otherwise.
        """
        try:
            self.logger.debug("Clearing all cached stock data.")
            with self.lock:
                self.cache.clear()
            self.logger.info("All cached stock data cleared successfully.")
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
            self.logger.debug("Closing StockMarketService resources.")
            # Currently, no persistent resources to close
            self.logger.info("StockMarketService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing StockMarketService: {e}", exc_info=True)
            raise StockMarketServiceError(f"Error closing StockMarketService: {e}")
