# services/game_control_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
import os
import subprocess
import psutil
import time
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager


class GameControlServiceError(Exception):
    """Custom exception for GameControlService-related errors."""
    pass


class GameControlService:
    """
    Provides game control capabilities, including launching games, monitoring game processes,
    managing game settings, and handling in-game events. Utilizes system-level operations and
    process management to ensure comprehensive game control functionalities. Ensures secure
    handling of game configurations and interactions.
    """

    def __init__(self):
        """
        Initializes the GameControlService with necessary configurations and authentication.
        """
        self.logger = setup_logging('GameControlService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.games: Dict[str, str] = {}  # Mapping of game names to executable paths
        self.active_games: Dict[str, psutil.Process] = {}
        self._load_games()
        self.logger.info("GameControlService initialized successfully.")

    def _load_games(self):
        """
        Loads the list of games and their executable paths from the configuration.
        """
        try:
            self.logger.debug("Loading games from configuration.")
            games_config = self.config_loader.get('GAMES_CONFIG', {})
            for game_name, exec_path_encrypted in games_config.items():
                exec_path = self.encryption_manager.decrypt_data(exec_path_encrypted).decode('utf-8')
                if os.path.isfile(exec_path):
                    self.games[game_name] = exec_path
                    self.logger.debug(f"Game '{game_name}' loaded with executable path '{exec_path}'.")
                else:
                    self.logger.warning(f"Executable path '{exec_path}' for game '{game_name}' does not exist.")
            self.logger.info(f"Total games loaded: {len(self.games)}.")
        except Exception as e:
            self.logger.error(f"Error loading games from configuration: {e}", exc_info=True)
            raise GameControlServiceError(f"Error loading games from configuration: {e}")

    def launch_game(self, game_name: str) -> bool:
        """
        Launches the specified game.

        Args:
            game_name (str): The name of the game to launch.

        Returns:
            bool: True if the game is launched successfully, False otherwise.
        """
        try:
            with self.lock:
                if game_name not in self.games:
                    self.logger.error(f"Game '{game_name}' is not available.")
                    return False
                exec_path = self.games[game_name]
                self.logger.debug(f"Launching game '{game_name}' from '{exec_path}'.")
                process = subprocess.Popen([exec_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.active_games[game_name] = psutil.Process(process.pid)
                self.logger.info(f"Game '{game_name}' launched successfully with PID {process.pid}.")
            return True
        except Exception as e:
            self.logger.error(f"Error launching game '{game_name}': {e}", exc_info=True)
            return False

    def close_game(self, game_name: str) -> bool:
        """
        Closes the specified game gracefully.

        Args:
            game_name (str): The name of the game to close.

        Returns:
            bool: True if the game is closed successfully, False otherwise.
        """
        try:
            with self.lock:
                if game_name not in self.active_games:
                    self.logger.warning(f"Game '{game_name}' is not currently running.")
                    return False
                process = self.active_games[game_name]
                self.logger.debug(f"Closing game '{game_name}' with PID {process.pid}.")
                process.terminate()
                process.wait(timeout=10)
                del self.active_games[game_name]
                self.logger.info(f"Game '{game_name}' closed successfully.")
            return True
        except psutil.NoSuchProcess:
            self.logger.warning(f"Process for game '{game_name}' does not exist.")
            return False
        except psutil.TimeoutExpired:
            self.logger.warning(f"Process for game '{game_name}' did not terminate in time. Killing now.")
            process.kill()
            del self.active_games[game_name]
            return True
        except Exception as e:
            self.logger.error(f"Error closing game '{game_name}': {e}", exc_info=True)
            return False

    def is_game_running(self, game_name: str) -> bool:
        """
        Checks if the specified game is currently running.

        Args:
            game_name (str): The name of the game to check.

        Returns:
            bool: True if the game is running, False otherwise.
        """
        try:
            with self.lock:
                if game_name in self.active_games:
                    process = self.active_games[game_name]
                    is_running = process.is_running() and not process.status() == psutil.STATUS_ZOMBIE
                    self.logger.debug(f"Game '{game_name}' running status: {is_running}.")
                    return is_running
                self.logger.debug(f"Game '{game_name}' is not running.")
                return False
        except Exception as e:
            self.logger.error(f"Error checking if game '{game_name}' is running: {e}", exc_info=True)
            return False

    def get_active_games(self) -> List[str]:
        """
        Retrieves a list of currently active (running) games.

        Returns:
            List[str]: A list of game names that are currently running.
        """
        try:
            with self.lock:
                running_games = [game for game, process in self.active_games.items()
                                if process.is_running() and not process.status() == psutil.STATUS_ZOMBIE]
                self.logger.debug(f"Active games: {running_games}.")
                return running_games
        except Exception as e:
            self.logger.error(f"Error retrieving active games: {e}", exc_info=True)
            return []

    def set_game_setting(self, game_name: str, setting: str, value: Any) -> bool:
        """
        Sets a specific setting for the specified game.

        Args:
            game_name (str): The name of the game to configure.
            setting (str): The setting to change.
            value (Any): The new value for the setting.

        Returns:
            bool: True if the setting is applied successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Setting '{setting}' to '{value}' for game '{game_name}'.")
            # Placeholder for actual game settings manipulation logic.
            # This could involve writing to config files, sending input commands, etc.
            # Implementation would depend on the game's API or configuration structure.
            # For demonstration, we'll assume it's a successful operation.
            # Replace this block with actual implementation as needed.
            self.logger.info(f"Setting '{setting}' applied to game '{game_name}' successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error setting '{setting}' for game '{game_name}': {e}", exc_info=True)
            return False

    def get_game_setting(self, game_name: str, setting: str) -> Optional[Any]:
        """
        Retrieves the value of a specific setting for the specified game.

        Args:
            game_name (str): The name of the game to query.
            setting (str): The setting to retrieve.

        Returns:
            Optional[Any]: The value of the setting, or None if retrieval fails.
        """
        try:
            self.logger.debug(f"Retrieving setting '{setting}' for game '{game_name}'.")
            # Placeholder for actual game settings retrieval logic.
            # This could involve reading from config files, querying the game's API, etc.
            # Implementation would depend on the game's API or configuration structure.
            # For demonstration, we'll assume a default value is returned.
            # Replace this block with actual implementation as needed.
            self.logger.info(f"Retrieved setting '{setting}' for game '{game_name}' successfully.")
            return "DefaultValue"
        except Exception as e:
            self.logger.error(f"Error retrieving setting '{setting}' for game '{game_name}': {e}", exc_info=True)
            return None

    def monitor_game_processes(self) -> None:
        """
        Continuously monitors active game processes and updates the active_games dictionary.
        """
        try:
            self.logger.debug("Starting game process monitoring.")
            while True:
                with self.lock:
                    for game_name, process in list(self.active_games.items()):
                        if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                            self.logger.info(f"Game '{game_name}' has terminated.")
                            del self.active_games[game_name]
                time.sleep(5)  # Polling interval
        except Exception as e:
            self.logger.error(f"Error monitoring game processes: {e}", exc_info=True)

    def start_monitoring(self) -> None:
        """
        Starts the game process monitoring in a separate thread.
        """
        try:
            self.logger.debug("Starting monitoring thread for game processes.")
            monitor_thread = threading.Thread(target=self.monitor_game_processes, daemon=True)
            monitor_thread.start()
            self.logger.info("Game process monitoring started successfully.")
        except Exception as e:
            self.logger.error(f"Error starting monitoring thread: {e}", exc_info=True)

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing GameControlService resources.")
            with self.lock:
                for game_name in list(self.active_games.keys()):
                    self.close_game(game_name)
            self.logger.info("GameControlService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing GameControlService: {e}", exc_info=True)
            raise GameControlServiceError(f"Error closing GameControlService: {e}")
