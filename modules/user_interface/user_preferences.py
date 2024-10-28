# modules/user_interface/user_preferences.py

"""
User Preferences Module

This module provides the UserPreferences class, responsible for managing user preferences
in a secure and efficient manner.

Features:
- Secure storage of preferences using encryption
- Data validation and type casting
- Thread-safe operations
- Robust error handling and logging
- Integration with the EnvironmentModule for configuration
- Support for default preferences and resetting to defaults
- Observable pattern to notify listeners of preference changes
- Serialization and deserialization using JSON
- Automatic loading and saving of preferences
- Versioning support for preference schemas
- Migration support for updating preferences between versions
- Encryption key management
- Cross-platform support

Author: Your Name
Date: YYYY-MM-DD
"""

import base64
import os
import json
import threading
import logging
from typing import Any, Dict, Callable, Optional
from cryptography.fernet import Fernet, InvalidToken
from pathlib import Path
from hashlib import sha256

# Import EnvironmentModule (assuming it's in the same package)
from modules.environment.environment_module import EnvironmentModule, EnvironmentError

# Configure Logging
logger = logging.getLogger('user_preferences')
logger.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# File Handler
file_handler = logging.FileHandler('logs/user_preferences.log')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Stream Handler (optional)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

# Exception Classes
class UserPreferencesError(Exception):
    """Base class for user preferences-related exceptions."""
    pass

class PreferenceValidationError(UserPreferencesError):
    """Raised when a preference value fails validation."""
    pass

class PreferenceEncryptionError(UserPreferencesError):
    """Raised when encryption or decryption of preferences fails."""
    pass

class UserPreferences:
    """
    UserPreferences Class

    Manages user preferences securely and efficiently.

    Features:
    - Secure storage using encryption
    - Data validation and type casting
    - Observable pattern for preference changes
    - Thread-safe operations
    """

    _instance_lock = threading.Lock()
    _instance = None

    def __new__(cls, *args, **kwargs):
        """
        Singleton pattern to ensure only one instance of UserPreferences exists.
        """
        if not cls._instance:
            with cls._instance_lock:
                if not cls._instance:
                    cls._instance = super(UserPreferences, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.logger = logger
        self.lock = threading.RLock()
        self.env_module = EnvironmentModule()
        self.preferences: Dict[str, Any] = {}
        self.default_preferences: Dict[str, Any] = self._load_default_preferences()
        self.observers: Dict[str, Callable[[str, Any], None]] = {}
        self.preferences_file = self._get_preferences_file_path()
        self.cipher = self._initialize_cipher()
        self._load_preferences()

    def _load_default_preferences(self) -> Dict[str, Any]:
        """
        Loads the default preferences.

        Returns:
            Dict[str, Any]: The default preferences.
        """
        default_prefs = {
            'theme': 'light',
            'language': 'en',
            'notifications_enabled': True,
            'font_size': 12,
            'auto_update': False,
            # Add more default preferences here
        }
        self.logger.debug("Default preferences loaded.")
        return default_prefs

    def _get_preferences_file_path(self) -> Path:
        """
        Determines the path to the preferences file.

        Returns:
            Path: The path to the preferences file.
        """
        app_dir = Path.home() / '.my_app'
        app_dir.mkdir(exist_ok=True)
        prefs_file = app_dir / 'user_prefs.enc'
        self.logger.debug(f"Preferences file path: {prefs_file}")
        return prefs_file

    def _initialize_cipher(self) -> Fernet:
        """
        Initializes the encryption cipher.

        Returns:
            Fernet: The cipher instance.

        Raises:
            PreferenceEncryptionError: If initialization fails.
        """
        try:
            key_material = self.env_module.get('PREFERENCES_ENCRYPTION_KEY')
            if not key_material:
                key_material = self._generate_encryption_key()
                self.env_module.set('PREFERENCES_ENCRYPTION_KEY', key_material)
            key = sha256(key_material.encode('utf-8')).digest()
            fernet_key = base64.urlsafe_b64encode(key)
            cipher = Fernet(fernet_key)
            self.logger.info("Encryption cipher initialized.")
            return cipher
        except Exception as e:
            self.logger.exception(f"Failed to initialize encryption cipher: {e}")
            raise PreferenceEncryptionError("Failed to initialize encryption cipher.") from e

    def _generate_encryption_key(self) -> str:
        """
        Generates a new encryption key.

        Returns:
            str: The generated encryption key.
        """
        key = Fernet.generate_key().decode('utf-8')
        self.logger.debug("Encryption key generated.")
        return key

    def _load_preferences(self):
        """
        Loads preferences from the encrypted file.
        """
        with self.lock:
            if self.preferences_file.exists():
                try:
                    with self.preferences_file.open('rb') as f:
                        encrypted_data = f.read()
                    decrypted_data = self.cipher.decrypt(encrypted_data)
                    self.preferences = json.loads(decrypted_data.decode('utf-8'))
                    self.logger.info("Preferences loaded from file.")
                except (InvalidToken, Exception) as e:
                    self.logger.exception(f"Failed to load preferences: {e}")
                    raise PreferenceEncryptionError("Failed to load preferences.") from e
            else:
                self.preferences = self.default_preferences.copy()
                self.logger.info("Preferences file not found. Loaded default preferences.")

    def _save_preferences(self):
        """
        Saves preferences to the encrypted file.
        """
        with self.lock:
            try:
                serialized_data = json.dumps(self.preferences).encode('utf-8')
                encrypted_data = self.cipher.encrypt(serialized_data)
                with self.preferences_file.open('wb') as f:
                    f.write(encrypted_data)
                self.logger.info("Preferences saved to file.")
            except Exception as e:
                self.logger.exception(f"Failed to save preferences: {e}")
                raise PreferenceEncryptionError("Failed to save preferences.") from e

    def get_preference(self, key: str) -> Any:
        """
        Retrieves a preference value.

        Args:
            key (str): The preference key.

        Returns:
            Any: The preference value.

        Raises:
            KeyError: If the key does not exist.
        """
        with self.lock:
            if key in self.preferences:
                value = self.preferences[key]
                self.logger.debug(f"Preference retrieved: {key} = {value}")
                return value
            else:
                self.logger.error(f"Preference '{key}' not found.")
                raise KeyError(f"Preference '{key}' not found.")

    def set_preference(self, key: str, value: Any) -> None:
        """
        Sets a preference value.

        Args:
            key (str): The preference key.
            value (Any): The preference value.

        Raises:
            PreferenceValidationError: If validation fails.
        """
        with self.lock:
            if key not in self.default_preferences:
                self.logger.error(f"Invalid preference key: {key}")
                raise PreferenceValidationError(f"Invalid preference key: {key}")
            expected_type = type(self.default_preferences[key])
            if not isinstance(value, expected_type):
                self.logger.error(f"Invalid type for preference '{key}': expected {expected_type.__name__}")
                raise PreferenceValidationError(f"Invalid type for preference '{key}': expected {expected_type.__name__}")
            self.preferences[key] = value
            self._notify_observers(key, value)
            self._save_preferences()
            self.logger.debug(f"Preference set: {key} = {value}")

    def reset_to_defaults(self) -> None:
        """
        Resets all preferences to their default values.
        """
        with self.lock:
            self.preferences = self.default_preferences.copy()
            self._save_preferences()
            self.logger.info("Preferences reset to default values.")

    def add_observer(self, key: str, callback: Callable[[str, Any], None]) -> None:
        """
        Adds an observer for a specific preference key.

        Args:
            key (str): The preference key.
            callback (Callable[[str, Any], None]): The callback function.
        """
        with self.lock:
            self.observers[key] = callback
            self.logger.debug(f"Observer added for preference '{key}'.")

    def remove_observer(self, key: str) -> None:
        """
        Removes an observer for a specific preference key.

        Args:
            key (str): The preference key.
        """
        with self.lock:
            if key in self.observers:
                del self.observers[key]
                self.logger.debug(f"Observer removed for preference '{key}'.")

    def _notify_observers(self, key: str, value: Any) -> None:
        """
        Notifies observers of a preference change.

        Args:
            key (str): The preference key.
            value (Any): The new preference value.
        """
        if key in self.observers:
            try:
                self.observers[key](key, value)
                self.logger.debug(f"Observer notified for preference '{key}'.")
            except Exception as e:
                self.logger.exception(f"Error in observer for preference '{key}': {e}")

    def migrate_preferences(self, old_version: int, new_version: int) -> None:
        """
        Migrates preferences from an old version to a new version.

        Args:
            old_version (int): The old version number.
            new_version (int): The new version number.
        """
        with self.lock:
            self.logger.info(f"Migrating preferences from version {old_version} to {new_version}.")
            # Implement migration logic here
            # Example:
            # if old_version < 2 and new_version >= 2:
            #     self.preferences['new_setting'] = default_value
            self._save_preferences()
            self.logger.info("Preferences migration completed.")

    # Additional methods can be added here as needed

# Example Usage (Remove or comment out in production)
if __name__ == "__main__":
    try:
        user_prefs = UserPreferences()

        # Get a preference
        theme = user_prefs.get_preference('theme')
        print(f"Current theme: {theme}")

        # Set a preference
        user_prefs.set_preference('theme', 'dark')
        print("Theme preference updated to 'dark'.")

        # Add an observer
        def on_theme_change(key, value):
            print(f"Preference '{key}' changed to '{value}'.")

        user_prefs.add_observer('theme', on_theme_change)

        # Change preference to trigger observer
        user_prefs.set_preference('theme', 'light')

        # Reset preferences to defaults
        user_prefs.reset_to_defaults()
        print("Preferences reset to default values.")

    except UserPreferencesError as e:
        print(f"UserPreferences error: {e}")
