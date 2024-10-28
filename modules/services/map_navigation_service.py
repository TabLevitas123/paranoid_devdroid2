# services/map_navigation_service.py

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple
import os
import requests
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

class MapNavigationServiceError(Exception):
    """Custom exception for MapNavigationService-related errors."""
    pass

class MapNavigationService:
    """
    Provides map navigation capabilities, including route planning, real-time traffic updates,
    geolocation services, and integration with mapping APIs. Utilizes external APIs like Google Maps
    or OpenStreetMap to deliver accurate and efficient navigation solutions. Ensures secure handling
    of API keys and user data.
    """

    def __init__(self):
        """
        Initializes the MapNavigationService with necessary configurations and authentication.
        """
        self.logger = setup_logging('MapNavigationService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.mapping_api_config = self._load_mapping_api_config()
        self.session = requests.Session()
        self.logger.info("MapNavigationService initialized successfully.")

    def _load_mapping_api_config(self) -> Dict[str, Any]:
        """
        Loads mapping API configurations securely.

        Returns:
            Dict[str, Any]: A dictionary containing mapping API configurations.
        """
        try:
            self.logger.debug("Loading mapping API configurations.")
            api_config_encrypted = self.config_loader.get('MAPPING_API_CONFIG', {})
            api_key_encrypted = api_config_encrypted.get('api_key')
            base_url = api_config_encrypted.get('base_url')
            if not api_key_encrypted or not base_url:
                self.logger.error("Mapping API configuration is incomplete.")
                raise MapNavigationServiceError("Mapping API configuration is incomplete.")
            api_key = self.encryption_manager.decrypt_data(api_key_encrypted).decode('utf-8')
            self.logger.debug("Mapping API configurations loaded successfully.")
            return {
                'api_key': api_key,
                'base_url': base_url
            }
        except Exception as e:
            self.logger.error(f"Error loading mapping API configurations: {e}", exc_info=True)
            raise MapNavigationServiceError(f"Error loading mapping API configurations: {e}")

    def plan_route(self, origin: Tuple[float, float], destination: Tuple[float, float], mode: str = 'driving') -> Optional[Dict[str, Any]]:
        """
        Plans a route from origin to destination using the specified mode of transportation.

        Args:
            origin (Tuple[float, float]): The latitude and longitude of the origin.
            destination (Tuple[float, float]): The latitude and longitude of the destination.
            mode (str, optional): Mode of transportation ('driving', 'walking', 'bicycling', 'transit'). Defaults to 'driving'.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing route details if successful, else None.
        """
        try:
            self.logger.debug(f"Planning route from {origin} to {destination} via {mode}.")
            with self.lock:
                params = {
                    'origin': f"{origin[0]},{origin[1]}",
                    'destination': f"{destination[0]},{destination[1]}",
                    'mode': mode,
                    'key': self.mapping_api_config['api_key']
                }
                response = self.session.get(f"{self.mapping_api_config['base_url']}/directions/json", params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data['status'] == 'OK':
                        route = data['routes'][0]
                        self.logger.info(f"Route planned successfully from {origin} to {destination}.")
                        return {
                            'summary': route['summary'],
                            'legs': route['legs'],
                            'overview_polyline': route['overview_polyline']['points']
                        }
                    else:
                        self.logger.error(f"Error in route planning: {data['status']} - {data.get('error_message', '')}")
                        return None
                else:
                    self.logger.error(f"Failed to plan route. HTTP Status Code: {response.status_code}")
                    return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception during route planning: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during route planning: {e}", exc_info=True)
            return None

    def get_real_time_traffic(self, location: Tuple[float, float]) -> Optional[Dict[str, Any]]:
        """
        Retrieves real-time traffic information for the specified location.

        Args:
            location (Tuple[float, float]): The latitude and longitude of the location.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing traffic details if successful, else None.
        """
        try:
            self.logger.debug(f"Fetching real-time traffic for location {location}.")
            with self.lock:
                params = {
                    'location': f"{location[0]},{location[1]}",
                    'radius': 10000,  # in meters
                    'key': self.mapping_api_config['api_key']
                }
                response = self.session.get(f"{self.mapping_api_config['base_url']}/traffic/json", params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    # Assuming the API provides traffic data in a specific format
                    self.logger.info(f"Real-time traffic data retrieved for location {location}.")
                    return data
                else:
                    self.logger.error(f"Failed to retrieve traffic data. HTTP Status Code: {response.status_code}")
                    return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception during traffic data retrieval: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during traffic data retrieval: {e}", exc_info=True)
            return None

    def geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Converts an address into geographical coordinates (latitude and longitude).

        Args:
            address (str): The address to geocode.

        Returns:
            Optional[Tuple[float, float]]: A tuple containing latitude and longitude if successful, else None.
        """
        try:
            self.logger.debug(f"Geocoding address: {address}.")
            with self.lock:
                params = {
                    'address': address,
                    'key': self.mapping_api_config['api_key']
                }
                response = self.session.get(f"{self.mapping_api_config['base_url']}/geocode/json", params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data['status'] == 'OK':
                        location = data['results'][0]['geometry']['location']
                        self.logger.info(f"Address '{address}' geocoded successfully to ({location['lat']}, {location['lng']}).")
                        return (location['lat'], location['lng'])
                    else:
                        self.logger.error(f"Error in geocoding address: {data['status']} - {data.get('error_message', '')}")
                        return None
                else:
                    self.logger.error(f"Failed to geocode address. HTTP Status Code: {response.status_code}")
                    return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception during geocoding: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during geocoding: {e}", exc_info=True)
            return None

    def reverse_geocode(self, coordinates: Tuple[float, float]) -> Optional[str]:
        """
        Converts geographical coordinates into a human-readable address.

        Args:
            coordinates (Tuple[float, float]): The latitude and longitude to reverse geocode.

        Returns:
            Optional[str]: The formatted address if successful, else None.
        """
        try:
            self.logger.debug(f"Reverse geocoding coordinates: {coordinates}.")
            with self.lock:
                params = {
                    'latlng': f"{coordinates[0]},{coordinates[1]}",
                    'key': self.mapping_api_config['api_key']
                }
                response = self.session.get(f"{self.mapping_api_config['base_url']}/geocode/json", params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data['status'] == 'OK':
                        address = data['results'][0]['formatted_address']
                        self.logger.info(f"Coordinates {coordinates} reverse geocoded successfully to '{address}'.")
                        return address
                    else:
                        self.logger.error(f"Error in reverse geocoding: {data['status']} - {data.get('error_message', '')}")
                        return None
                else:
                    self.logger.error(f"Failed to reverse geocode coordinates. HTTP Status Code: {response.status_code}")
                    return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception during reverse geocoding: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during reverse geocoding: {e}", exc_info=True)
            return None

    def get_nearby_points_of_interest(self, location: Tuple[float, float], radius: int = 1000, types: Optional[List[str]] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves a list of nearby points of interest based on the provided location.

        Args:
            location (Tuple[float, float]): The latitude and longitude of the location.
            radius (int, optional): The search radius in meters. Defaults to 1000.
            types (Optional[List[str]], optional): List of POI types to filter. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of POIs if successful, else None.
        """
        try:
            self.logger.debug(f"Fetching nearby points of interest for location {location} within radius {radius} meters.")
            with self.lock:
                params = {
                    'location': f"{location[0]},{location[1]}",
                    'radius': radius,
                    'key': self.mapping_api_config['api_key']
                }
                if types:
                    params['types'] = '|'.join(types)
                response = self.session.get(f"{self.mapping_api_config['base_url']}/places/nearbysearch/json", params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data['status'] == 'OK':
                        pois = data['results']
                        self.logger.info(f"Retrieved {len(pois)} points of interest for location {location}.")
                        return pois
                    else:
                        self.logger.error(f"Error fetching POIs: {data['status']} - {data.get('error_message', '')}")
                        return None
                else:
                    self.logger.error(f"Failed to fetch POIs. HTTP Status Code: {response.status_code}")
                    return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception during POI retrieval: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during POI retrieval: {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing MapNavigationService resources.")
            self.session.close()
            self.logger.info("MapNavigationService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing MapNavigationService: {e}", exc_info=True)
            raise MapNavigationServiceError(f"Error closing MapNavigationService: {e}")
