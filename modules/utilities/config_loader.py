# utilities/config_loader.py

import logging
import os
import json
from typing import Any, Dict
from modules.utilities.logging_manager import setup_logging

class ConfigLoader:
    """
    Loads and manages configuration settings from JSON files and environment variables.
    Ensures that configurations are securely loaded and validated.
    """

    def __init__(self, config_file: str = 'config/config.json'):
        """
        Initializes the ConfigLoader with the path to the configuration file.

        Args:
            config_file (str, optional): Path to the JSON configuration file. Defaults to 'config/config.json'.
        """
        self.logger = setup_logging('ConfigLoader')
        self.config_file = config_file
        self.config = {}
        self.logger.info(f"ConfigLoader initialized with config file: {self.config_file}")
        self.load_config()

    def load_config(self) -> None:
        """
        Loads configuration settings from the JSON file and environment variables.
        """
        try:
            self.logger.debug("Loading configuration from file.")
            self._load_from_file()
            self.logger.debug("Loading configuration from environment variables.")
            self._load_from_env()
            self.logger.info("Configuration loaded successfully.")
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}", exc_info=True)
            raise

    def _load_from_file(self) -> None:
        """
        Loads configuration settings from a JSON file.
        """
        try:
            if not os.path.exists(self.config_file):
                self.logger.error(f"Configuration file not found: {self.config_file}")
                raise FileNotFoundError(f"Configuration file not found: {self.config_file}")
            with open(self.config_file, 'r') as f:
                file_config = json.load(f)
            self.config.update(file_config)
            self.logger.debug("Configuration loaded from file successfully.")
        except json.JSONDecodeError as jde:
            self.logger.error(f"JSON decode error in configuration file: {jde}", exc_info=True)
            raise
        except Exception as e:
            self.logger.error(f"Error loading configuration from file: {e}", exc_info=True)
            raise

    def _load_from_env(self) -> None:
        """
        Overrides configuration settings with environment variables if they exist.
        Environment variables take precedence over file configurations.
        """
        try:
            env_config = {key: value for key, value in os.environ.items() if key.startswith('APP_')}
            if env_config:
                self.config.update(env_config)
                self.logger.debug("Configuration overridden with environment variables successfully.")
        except Exception as e:
            self.logger.error(f"Error loading configuration from environment variables: {e}", exc_info=True)
            raise

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a configuration value by key.

        Args:
            key (str): The configuration key.
            default (Any, optional): The default value if key is not found. Defaults to None.

        Returns:
            Any: The configuration value.
        """
        try:
            value = self.config.get(key, default)
            self.logger.debug(f"Retrieved config '{key}': {value}")
            return value
        except Exception as e:
            self.logger.error(f"Error retrieving config '{key}': {e}", exc_info=True)
            return default

    def get_all(self) -> Dict[str, Any]:
        """
        Retrieves the entire configuration dictionary.

        Returns:
            Dict[str, Any]: The configuration settings.
        """
        try:
            self.logger.debug("Retrieving all configuration settings.")
            return self.config.copy()
        except Exception as e:
            self.logger.error(f"Error retrieving all configuration settings: {e}", exc_info=True)
            return {}

    def validate_config(self, required_keys: list) -> bool:
        """
        Validates that all required configuration keys are present.

        Args:
            required_keys (list): A list of required configuration keys.

        Returns:
            bool: True if all required keys are present, False otherwise.
        """
        try:
            self.logger.debug("Validating configuration settings.")
            missing_keys = [key for key in required_keys if key not in self.config]
            if missing_keys:
                self.logger.error(f"Missing configuration keys: {missing_keys}")
                return False
            self.logger.info("All required configuration keys are present.")
            return True
        except Exception as e:
            self.logger.error(f"Error validating configuration: {e}", exc_info=True)
            return False

    def reload_config(self) -> None:
        """
        Reloads the configuration settings from the file and environment variables.
        Useful for applying configuration changes without restarting the application.
        """
        try:
            self.logger.info("Reloading configuration settings.")
            self.config.clear()
            self.load_config()
            self.logger.info("Configuration reloaded successfully.")
        except Exception as e:
            self.logger.error(f"Error reloading configuration: {e}", exc_info=True)
            raise
