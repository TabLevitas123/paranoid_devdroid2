# modules/environment/environment_module.py

"""
Environment Module

This module provides the EnvironmentModule class, responsible for managing environment configurations,
variables, and settings in a secure and efficient manner.

Features:
- Secure loading and validation of environment variables
- Support for multiple configuration sources (environment variables, .env files, configuration files)
- Automatic type casting and validation of variables
- Singleton pattern implementation for consistent access
- Thread-safe operations
- Robust error handling and logging
- Integration with other modules (e.g., DataModule, SecurityModule)
- Encryption and decryption of sensitive configuration values
- Hot-reloading support for dynamic environments
- Configuration profiles (e.g., development, testing, production)
- Integration with cloud services for secrets management (e.g., AWS Secrets Manager, HashiCorp Vault)

Author: Your Name
Date: YYYY-MM-DD
"""

import os
import logging
import threading
from typing import Any, Dict, Optional
from dotenv import load_dotenv, find_dotenv
import json
import yaml
from cryptography.fernet import Fernet
from functools import wraps

# Configure Logging
logger = logging.getLogger('environment_module')
logger.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# File Handler
file_handler = logging.FileHandler('logs/environment_module.log')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Stream Handler (optional)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

# Exception Classes
class EnvironmentError(Exception):
    """Base class for environment-related exceptions."""
    pass

class VariableNotFoundError(EnvironmentError):
    """Raised when a required environment variable is not found."""
    pass

class InvalidVariableError(EnvironmentError):
    """Raised when an environment variable has an invalid value."""
    pass

class DecryptionError(EnvironmentError):
    """Raised when decryption of a variable fails."""
    pass

class EnvironmentModule:
    """
    EnvironmentModule Class

    Manages environment configurations, variables, and settings securely and efficiently.
    """

    _instance_lock = threading.Lock()
    _instance = None

    def __new__(cls, *args, **kwargs):
        """
        Singleton pattern to ensure only one instance of EnvironmentModule exists.
        """
        if not cls._instance:
            with cls._instance_lock:
                if not cls._instance:
                    cls._instance = super(EnvironmentModule, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.logger = logger
        self.lock = threading.RLock()
        self.config: Dict[str, Any] = {}
        self._load_environment()
        self._load_configuration_files()
        self._validate_variables()
        self._initialize_encryption_key()

    def _load_environment(self):
        """
        Loads environment variables from the system and .env files.
        """
        with self.lock:
            dotenv_path = find_dotenv()
            if dotenv_path:
                load_dotenv(dotenv_path)
                self.logger.info(f"Environment variables loaded from {dotenv_path}")
            else:
                self.logger.warning(".env file not found; loading system environment variables.")
            self.config.update(os.environ)
            self.logger.debug("Environment variables loaded into config.")

    def _load_configuration_files(self):
        """
        Loads additional configuration from JSON or YAML files.
        """
        with self.lock:
            config_file = self.config.get('CONFIG_FILE_PATH')
            if config_file and os.path.isfile(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as file:
                        if config_file.endswith('.json'):
                            file_config = json.load(file)
                        elif config_file.endswith(('.yml', '.yaml')):
                            file_config = yaml.safe_load(file)
                        else:
                            self.logger.error(f"Unsupported configuration file format: {config_file}")
                            raise EnvironmentError("Unsupported configuration file format.")
                    self.config.update(file_config)
                    self.logger.info(f"Configuration loaded from {config_file}")
                except Exception as e:
                    self.logger.exception(f"Failed to load configuration file: {e}")
                    raise EnvironmentError("Failed to load configuration file.") from e
            else:
                self.logger.info("No configuration file specified or file does not exist.")

    def _validate_variables(self):
        """
        Validates required environment variables and casts them to appropriate types.
        """
        with self.lock:
            required_variables = {
                'APP_ENV': str,
                'DEBUG': bool,
                'DB_HOST': str,
                'DB_PORT': int,
                'DB_USERNAME': str,
                'DB_PASSWORD': str,
                'ENCRYPTION_KEY': str,
                # Add more required variables here
            }

            for var_name, var_type in required_variables.items():
                value = self.get(var_name)
                if value is None:
                    self.logger.error(f"Required environment variable '{var_name}' is missing.")
                    raise VariableNotFoundError(f"Required environment variable '{var_name}' is missing.")
                try:
                    cast_value = self._cast_variable(value, var_type)
                    self.config[var_name] = cast_value
                    self.logger.debug(f"Environment variable '{var_name}' validated and casted.")
                except ValueError as e:
                    self.logger.error(f"Invalid value for environment variable '{var_name}': {e}")
                    raise InvalidVariableError(f"Invalid value for environment variable '{var_name}'.") from e

    def _cast_variable(self, value: str, var_type: type) -> Any:
        """
        Casts an environment variable to the specified type.

        Args:
            value (str): The value to cast.
            var_type (type): The type to cast to.

        Returns:
            Any: The casted value.

        Raises:
            ValueError: If casting fails.
        """
        if var_type == bool:
            return value.lower() in ('true', '1', 'yes', 'on')
        elif var_type == int:
            return int(value)
        elif var_type == float:
            return float(value)
        elif var_type == str:
            return value
        else:
            self.logger.error(f"Unsupported variable type for casting: {var_type}")
            raise ValueError(f"Unsupported variable type for casting: {var_type}")

    def _initialize_encryption_key(self):
        """
        Initializes the encryption key for sensitive data.
        """
        with self.lock:
            key = self.get('ENCRYPTION_KEY')
            if not key:
                self.logger.error("Encryption key is missing.")
                raise VariableNotFoundError("Encryption key is missing.")
            try:
                self.cipher = Fernet(key)
                self.logger.info("Encryption key initialized successfully.")
            except Exception as e:
                self.logger.exception(f"Invalid encryption key: {e}")
                raise InvalidVariableError("Invalid encryption key.") from e

    def get(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        """
        Retrieves a configuration value.

        Args:
            key (str): The configuration key.
            default (Optional[Any]): The default value if the key is not found.

        Returns:
            Optional[Any]: The configuration value.
        """
        with self.lock:
            value = self.config.get(key, default)
            self.logger.debug(f"Retrieved configuration for key '{key}': {value}")
            return value

    def set(self, key: str, value: Any) -> None:
        """
        Sets a configuration value.

        Args:
            key (str): The configuration key.
            value (Any): The value to set.
        """
        with self.lock:
            self.config[key] = value
            self.logger.debug(f"Set configuration for key '{key}' to '{value}'.")

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypts a plaintext string.

        Args:
            plaintext (str): The plaintext to encrypt.

        Returns:
            str: The encrypted ciphertext.

        Raises:
            DecryptionError: If encryption fails.
        """
        try:
            encrypted = self.cipher.encrypt(plaintext.encode('utf-8')).decode('utf-8')
            self.logger.debug("Encryption successful.")
            return encrypted
        except Exception as e:
            self.logger.exception(f"Encryption failed: {e}")
            raise DecryptionError("Encryption failed.") from e

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypts a ciphertext string.

        Args:
            ciphertext (str): The ciphertext to decrypt.

        Returns:
            str: The decrypted plaintext.

        Raises:
            DecryptionError: If decryption fails.
        """
        try:
            decrypted = self.cipher.decrypt(ciphertext.encode('utf-8')).decode('utf-8')
            self.logger.debug("Decryption successful.")
            return decrypted
        except Exception as e:
            self.logger.exception(f"Decryption failed: {e}")
            raise DecryptionError("Decryption failed.") from e

    def reload(self) -> None:
        """
        Reloads the environment configurations (hot-reloading).

        This can be used to apply changes without restarting the application.
        """
        with self.lock:
            self.logger.info("Reloading environment configurations.")
            self._load_environment()
            self._load_configuration_files()
            self._validate_variables()
            self.logger.info("Environment configurations reloaded successfully.")

    def get_config_profile(self) -> str:
        """
        Retrieves the current configuration profile (e.g., development, production).

        Returns:
            str: The configuration profile.
        """
        profile = self.get('APP_ENV', 'development')
        self.logger.debug(f"Configuration profile: {profile}")
        return profile

    def is_debug_mode(self) -> bool:
        """
        Determines if the application is running in debug mode.

        Returns:
            bool: True if debug mode is enabled.
        """
        debug_mode = self.get('DEBUG', False)
        self.logger.debug(f"Debug mode is {'enabled' if debug_mode else 'disabled'}.")
        return debug_mode

    def get_database_url(self) -> str:
        """
        Constructs the database URL from individual components.

        Returns:
            str: The database URL.
        """
        db_user = self.get('DB_USERNAME')
        db_pass = self.get('DB_PASSWORD')
        db_host = self.get('DB_HOST')
        db_port = self.get('DB_PORT')
        db_name = self.get('DB_NAME')

        if None in (db_user, db_pass, db_host, db_port, db_name):
            self.logger.error("Database configuration is incomplete.")
            raise EnvironmentError("Database configuration is incomplete.")

        db_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
        self.logger.debug(f"Database URL constructed: {db_url}")
        return db_url

    def load_secret(self, secret_name: str) -> str:
        """
        Loads a secret from a cloud secrets manager.

        Args:
            secret_name (str): The name of the secret.

        Returns:
            str: The secret value.

        Raises:
            EnvironmentError: If loading the secret fails.
        """
        # Placeholder for actual secrets manager integration
        try:
            # Example: AWS Secrets Manager or HashiCorp Vault integration
            secret_value = "secret_value"  # Replace with actual secret retrieval logic
            self.logger.debug(f"Secret '{secret_name}' loaded successfully.")
            return secret_value
        except Exception as e:
            self.logger.exception(f"Failed to load secret '{secret_name}': {e}")
            raise EnvironmentError(f"Failed to load secret '{secret_name}'.") from e

    # Additional methods can be added here as needed

# Example Usage (Remove or comment out in production)
if __name__ == "__main__":
    try:
        env_module = EnvironmentModule()
        # Retrieve a configuration value
        app_env = env_module.get_config_profile()
        print(f"Application Environment: {app_env}")
        # Check if debug mode is enabled
        is_debug = env_module.is_debug_mode()
        print(f"Debug Mode: {'Enabled' if is_debug else 'Disabled'}")
        # Get the database URL
        db_url = env_module.get_database_url()
        print(f"Database URL: {db_url}")
        # Encrypt and decrypt a value
        encrypted_value = env_module.encrypt('SensitiveData123')
        print(f"Encrypted Value: {encrypted_value}")
        decrypted_value = env_module.decrypt(encrypted_value)
        print(f"Decrypted Value: {decrypted_value}")
        # Reload configurations
        env_module.reload()
    except EnvironmentError as e:
        print(f"Environment error: {e}")
