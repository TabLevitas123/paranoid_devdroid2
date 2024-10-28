# services/weather_service.py

import logging
import threading
import time
from typing import Any, Dict, Optional
import requests
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

class WeatherServiceError(Exception):
    """Custom exception for WeatherService-related errors."""
    pass

class WeatherService:
    """
    Provides weather data retrieval capabilities by interfacing with external weather APIs.
    Handles fetching current weather, forecasts, and historical data with robust error handling and caching.
    Ensures secure handling of API keys and configurations.
    """

    def __init__(self):
        """
        Initializes the WeatherService with necessary configurations and authentication.
        """
        self.logger = setup_logging('WeatherService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.api_key = self._load_api_key()
        self.base_url = self.config_loader.get('WEATHER_API_BASE_URL', 'https://api.openweathermap.org/data/2.5')
        self.cache_duration = self.config_loader.get('WEATHER_CACHE_DURATION', 600)  # in seconds
        self.cache: Dict[str, Any] = {}
        self.lock = threading.Lock()
        self.logger.info("WeatherService initialized successfully.")

    def _load_api_key(self) -> str:
        """
        Loads and decrypts the weather API key from the configuration.

        Returns:
            str: The decrypted API key.

        Raises:
            WeatherServiceError: If the API key is missing or decryption fails.
        """
        try:
            self.logger.debug("Loading weather API key from configuration.")
            encrypted_key = self.config_loader.get('WEATHER_API_KEY_ENCRYPTED')
            if not encrypted_key:
                self.logger.error("WEATHER_API_KEY_ENCRYPTED not found in configuration.")
                raise WeatherServiceError("WEATHER_API_KEY_ENCRYPTED not found in configuration.")
            decrypted_key = self.encryption_manager.decrypt_data(encrypted_key).decode('utf-8')
            self.logger.debug("Weather API key decrypted successfully.")
            return decrypted_key
        except Exception as e:
            self.logger.error(f"Error loading weather API key: {e}", exc_info=True)
            raise WeatherServiceError(f"Error loading weather API key: {e}")

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

    def _fetch_weather_data(self, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Fetches weather data from the external API with caching.

        Args:
            endpoint (str): The API endpoint.
            params (Dict[str, Any]): The query parameters.

        Returns:
            Optional[Dict[str, Any]]: The weather data, or None if fetching fails.
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
        params['appid'] = self.api_key
        try:
            self.logger.debug(f"Fetching weather data from '{url}' with params: {params}")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            with self.lock:
                self.cache[cache_key] = (data, time.time())
            self.logger.info(f"Weather data fetched successfully from '{url}'.")
            return data
        except requests.exceptions.RequestException as e:
            self.logger.error(f"HTTP request error when fetching weather data: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error when fetching weather data: {e}", exc_info=True)
            return None

    def get_current_weather(self, location: str, units: str = 'metric') -> Optional[Dict[str, Any]]:
        """
        Retrieves the current weather data for a specified location.

        Args:
            location (str): The location for which to retrieve weather data (e.g., city name).
            units (str, optional): The units of measurement ('metric', 'imperial', 'standard'). Defaults to 'metric'.

        Returns:
            Optional[Dict[str, Any]]: The current weather data, or None if retrieval fails.
        """
        endpoint = 'weather'
        params = {'q': location, 'units': units}
        return self._fetch_weather_data(endpoint, params)

    def get_forecast(self, location: str, days: int = 5, units: str = 'metric') -> Optional[Dict[str, Any]]:
        """
        Retrieves the weather forecast data for a specified location.

        Args:
            location (str): The location for which to retrieve the forecast (e.g., city name).
            days (int, optional): The number of days to forecast (1-7). Defaults to 5.
            units (str, optional): The units of measurement ('metric', 'imperial', 'standard'). Defaults to 'metric'.

        Returns:
            Optional[Dict[str, Any]]: The weather forecast data, or None if retrieval fails.
        """
        endpoint = 'forecast/daily'
        params = {'q': location, 'cnt': days, 'units': units}
        return self._fetch_weather_data(endpoint, params)

    def get_historical_weather(self, location: str, start_date: str, end_date: str, units: str = 'metric') -> Optional[Dict[str, Any]]:
        """
        Retrieves historical weather data for a specified location and date range.

        Args:
            location (str): The location for which to retrieve historical weather data (e.g., city name).
            start_date (str): The start date in 'YYYY-MM-DD' format.
            end_date (str): The end date in 'YYYY-MM-DD' format.
            units (str, optional): The units of measurement ('metric', 'imperial', 'standard'). Defaults to 'metric'.

        Returns:
            Optional[Dict[str, Any]]: The historical weather data, or None if retrieval fails.
        """
        endpoint = 'onecall/timemachine'
        # Note: OpenWeatherMap's One Call API requires latitude and longitude
        coords = self._get_coordinates(location)
        if not coords:
            self.logger.error(f"Could not retrieve coordinates for location '{location}'.")
            return None
        from datetime import datetime
        import time
        try:
            start_timestamp = int(time.mktime(datetime.strptime(start_date, '%Y-%m-%d').timetuple()))
            end_timestamp = int(time.mktime(datetime.strptime(end_date, '%Y-%m-%d').timetuple()))
        except ValueError as e:
            self.logger.error(f"Invalid date format: {e}", exc_info=True)
            return None

        # Note: OpenWeatherMap's API may not support a range of dates directly; this is a simplified example
        historical_data = {}
        for timestamp in range(start_timestamp, end_timestamp + 1, 86400):  # Increment by one day
            params = {
                'lat': coords['lat'],
                'lon': coords['lon'],
                'dt': timestamp,
                'units': units
            }
            data = self._fetch_weather_data(endpoint, params)
            if data:
                historical_data[datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')] = data
        if historical_data:
            self.logger.info(f"Historical weather data retrieved successfully for '{location}'.")
            return historical_data
        else:
            self.logger.warning(f"No historical weather data retrieved for '{location}'.")
            return None

    def _get_coordinates(self, location: str) -> Optional[Dict[str, float]]:
        """
        Retrieves the geographical coordinates for a given location.

        Args:
            location (str): The location name (e.g., city name).

        Returns:
            Optional[Dict[str, float]]: A dictionary with 'lat' and 'lon', or None if retrieval fails.
        """
        endpoint = 'weather'
        params = {'q': location}
        data = self._fetch_weather_data(endpoint, params)
        if data and 'coord' in data:
            self.logger.debug(f"Coordinates for '{location}': {data['coord']}")
            return data['coord']
        else:
            self.logger.error(f"Could not retrieve coordinates for location '{location}'.")
            return None

    def list_cached_data(self) -> Dict[str, Any]:
        """
        Lists all cached weather data.

        Returns:
            Dict[str, Any]: A dictionary of cached data keys and their timestamps.
        """
        try:
            self.logger.debug("Listing all cached weather data.")
            cached_keys = {key: value[1] for key, value in self.cache.items()}
            self.logger.info(f"Retrieved {len(cached_keys)} cached weather data entries.")
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
        Clears all cached weather data.

        Returns:
            bool: True if all cache entries are cleared successfully, False otherwise.
        """
        try:
            self.logger.debug("Clearing all cached weather data.")
            with self.lock:
                self.cache.clear()
            self.logger.info("All cached weather data cleared successfully.")
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
            self.logger.debug("Closing WeatherService resources.")
            # Currently, no persistent resources to close
            self.logger.info("WeatherService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing WeatherService: {e}", exc_info=True)
            raise WeatherServiceError(f"Error closing WeatherService: {e}")
