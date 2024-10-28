# services/smart_home_service.py

import logging
import threading
from typing import Any, Dict, List, Optional, Callable
import os
import json

import requests
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from services.iot_control_service import IoTControlService


class SmartHomeServiceError(Exception):
    """Custom exception for SmartHomeService-related errors."""
    pass


class SmartHomeService:
    """
    Provides comprehensive smart home management capabilities, including orchestrating multiple IoT devices,
    managing user preferences, automating routines and scenes, integrating with virtual assistants, and
    providing a centralized dashboard for monitoring and control. Utilizes the IoTControlService for
    device interactions and ensures secure handling of user data and configurations.
    """

    def __init__(self):
        """
        Initializes the SmartHomeService with necessary configurations and authentication.
        """
        self.logger = setup_logging('SmartHomeService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.iot_service = IoTControlService()
        self.scenes: Dict[str, Dict[str, Any]] = {}  # Mapping of scene names to device commands
        self.user_preferences: Dict[str, Any] = {}  # Mapping of user IDs to their preferences
        self._load_scenes()
        self.logger.info("SmartHomeService initialized successfully.")

    def _load_scenes(self):
        """
        Loads predefined scenes from the configuration.
        """
        try:
            self.logger.debug("Loading scenes from configuration.")
            scenes_config = self.config_loader.get('SCENES_CONFIG', {})
            for scene_name, commands in scenes_config.items():
                self.scenes[scene_name] = commands
                self.logger.debug(f"Scene '{scene_name}' loaded with commands: {commands}.")
            self.logger.info(f"Total scenes loaded: {len(self.scenes)}.")
        except Exception as e:
            self.logger.error(f"Error loading scenes from configuration: {e}", exc_info=True)
            raise SmartHomeServiceError(f"Error loading scenes from configuration: {e}")

    def create_scene(self, scene_name: str, device_commands: Dict[str, Dict[str, Any]]) -> bool:
        """
        Creates a new scene with specified device commands.

        Args:
            scene_name (str): The name of the scene.
            device_commands (Dict[str, Dict[str, Any]]): Mapping of device IDs to their respective commands.

        Returns:
            bool: True if the scene is created successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Creating scene '{scene_name}' with commands: {device_commands}.")
            with self.lock:
                if scene_name in self.scenes:
                    self.logger.error(f"Scene '{scene_name}' already exists.")
                    return False
                self.scenes[scene_name] = device_commands
                self._save_scenes()
                self.logger.info(f"Scene '{scene_name}' created successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error creating scene '{scene_name}': {e}", exc_info=True)
            return False

    def _save_scenes(self):
        """
        Saves the current scenes to the configuration file.
        """
        try:
            self.logger.debug("Saving scenes to configuration.")
            scenes_config = self.scenes
            config_path = self.config_loader.get_config_path('SCENES_CONFIG')
            with open(config_path, 'w') as f:
                json.dump(scenes_config, f, indent=4)
            self.logger.debug("Scenes saved successfully.")
        except Exception as e:
            self.logger.error(f"Error saving scenes to configuration: {e}", exc_info=True)
            raise SmartHomeServiceError(f"Error saving scenes to configuration: {e}")

    def activate_scene(self, scene_name: str) -> bool:
        """
        Activates a predefined scene by sending commands to all associated devices.

        Args:
            scene_name (str): The name of the scene to activate.

        Returns:
            bool: True if the scene is activated successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Activating scene '{scene_name}'.")
            with self.lock:
                if scene_name not in self.scenes:
                    self.logger.error(f"Scene '{scene_name}' does not exist.")
                    return False
                device_commands = self.scenes[scene_name]
                for device_id, command in device_commands.items():
                    self.iot_service.send_command(device_id, command)
                self.logger.info(f"Scene '{scene_name}' activated successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error activating scene '{scene_name}': {e}", exc_info=True)
            return False

    def delete_scene(self, scene_name: str) -> bool:
        """
        Deletes an existing scene.

        Args:
            scene_name (str): The name of the scene to delete.

        Returns:
            bool: True if the scene is deleted successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Deleting scene '{scene_name}'.")
            with self.lock:
                if scene_name not in self.scenes:
                    self.logger.error(f"Scene '{scene_name}' does not exist.")
                    return False
                del self.scenes[scene_name]
                self._save_scenes()
                self.logger.info(f"Scene '{scene_name}' deleted successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error deleting scene '{scene_name}': {e}", exc_info=True)
            return False

    def set_user_preference(self, user_id: str, preference: str, value: Any) -> bool:
        """
        Sets a user preference for smart home configurations.

        Args:
            user_id (str): The unique identifier of the user.
            preference (str): The preference name.
            value (Any): The preference value.

        Returns:
            bool: True if the preference is set successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Setting preference '{preference}' to '{value}' for user '{user_id}'.")
            with self.lock:
                if user_id not in self.user_preferences:
                    self.user_preferences[user_id] = {}
                self.user_preferences[user_id][preference] = value
                self._save_user_preferences()
                self.logger.info(f"Preference '{preference}' set to '{value}' for user '{user_id}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error setting preference '{preference}' for user '{user_id}': {e}", exc_info=True)
            return False

    def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the preferences for a specific user.

        Args:
            user_id (str): The unique identifier of the user.

        Returns:
            Optional[Dict[str, Any]]: The user's preferences, or None if retrieval fails.
        """
        try:
            self.logger.debug(f"Retrieving preferences for user '{user_id}'.")
            with self.lock:
                preferences = self.user_preferences.get(user_id)
                if preferences is None:
                    self.logger.warning(f"No preferences found for user '{user_id}'.")
                else:
                    self.logger.debug(f"Preferences for user '{user_id}': {preferences}.")
            return preferences
        except Exception as e:
            self.logger.error(f"Error retrieving preferences for user '{user_id}': {e}", exc_info=True)
            return None

    def _save_user_preferences(self):
        """
        Saves the current user preferences to the configuration file.
        """
        try:
            self.logger.debug("Saving user preferences to configuration.")
            config_path = self.config_loader.get_config_path('USER_PREFERENCES_CONFIG')
            with open(config_path, 'w') as f:
                json.dump(self.user_preferences, f, indent=4)
            self.logger.debug("User preferences saved successfully.")
        except Exception as e:
            self.logger.error(f"Error saving user preferences to configuration: {e}", exc_info=True)
            raise SmartHomeServiceError(f"Error saving user preferences to configuration: {e}")

    def automate_routine(self, routine_name: str, actions: List[Callable[[str], bool]]) -> bool:
        """
        Automates a routine by executing a sequence of actions.

        Args:
            routine_name (str): The name of the routine.
            actions (List[Callable[[str], bool]]): A list of action functions to execute.

        Returns:
            bool: True if the routine is executed successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Automating routine '{routine_name}' with actions: {actions}.")
            with self.lock:
                for action in actions:
                    if not action(routine_name):
                        self.logger.error(f"Action '{action.__name__}' failed during routine '{routine_name}'.")
                        return False
                self.logger.info(f"Routine '{routine_name}' executed successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error automating routine '{routine_name}': {e}", exc_info=True)
            return False

    def integrate_with_virtual_assistant(self, virtual_assistant_api_url: str, virtual_assistant_api_key: str) -> bool:
        """
        Integrates with a virtual assistant API to handle voice commands for smart home control.

        Args:
            virtual_assistant_api_url (str): The API endpoint of the virtual assistant.
            virtual_assistant_api_key (str): The API key for authenticating with the virtual assistant.

        Returns:
            bool: True if integration is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Integrating with virtual assistant at '{virtual_assistant_api_url}'.")
            headers = {
                'Authorization': f"Bearer {virtual_assistant_api_key}",
                'Content-Type': 'application/json'
            }
            data = {
                'service': 'smart_home',
                'actions': list(self.scenes.keys())
            }
            response = requests.post(virtual_assistant_api_url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                self.logger.info("Integrated with virtual assistant successfully.")
                return True
            else:
                self.logger.error(f"Failed to integrate with virtual assistant: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"Error integrating with virtual assistant at '{virtual_assistant_api_url}': {e}", exc_info=True)
            return False

    def trigger_event_based_automation(self, event: str, callback: Callable[[str], bool]) -> bool:
        """
        Sets up event-based automation by linking events to specific actions.

        Args:
            event (str): The event name to listen for.
            callback (Callable[[str], bool]): The action to execute when the event occurs.

        Returns:
            bool: True if automation is set up successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Setting up event-based automation for event '{event}'.")
            # Placeholder for event subscription and callback linkage
            # Implementation would depend on the event source and system architecture
            # For demonstration, we'll assume it's a successful setup
            # Replace this block with actual implementation as needed.
            self.logger.info(f"Event-based automation for event '{event}' set up successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error setting up event-based automation for event '{event}': {e}", exc_info=True)
            return False

    def list_scenes(self) -> List[str]:
        """
        Retrieves a list of all available scenes.

        Returns:
            List[str]: A list of scene names.
        """
        try:
            with self.lock:
                scene_list = list(self.scenes.keys())
            self.logger.debug(f"Available scenes: {scene_list}.")
            return scene_list
        except Exception as e:
            self.logger.error(f"Error listing scenes: {e}", exc_info=True)
            return []

    def list_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the preferences for a specific user.

        Args:
            user_id (str): The unique identifier of the user.

        Returns:
            Optional[Dict[str, Any]]: The user's preferences, or None if retrieval fails.
        """
        try:
            preferences = self.iot_service.get_user_preferences(user_id)
            if preferences:
                self.logger.debug(f"User '{user_id}' preferences: {preferences}.")
                return preferences
            else:
                self.logger.warning(f"No preferences found for user '{user_id}'.")
                return None
        except Exception as e:
            self.logger.error(f"Error retrieving preferences for user '{user_id}': {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing SmartHomeService resources.")
            self.iot_service.close_service()
            self.logger.info("SmartHomeService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing SmartHomeService: {e}", exc_info=True)
            raise SmartHomeServiceError(f"Error closing SmartHomeService: {e}")
