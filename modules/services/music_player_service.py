# services/music_player_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
import os
import pygame
from pygame import mixer
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager


class MusicPlayerServiceError(Exception):
    """Custom exception for MusicPlayerService-related errors."""
    pass


class MusicPlayerService:
    """
    Provides music playback capabilities, including playing, pausing, stopping tracks,
    managing playlists, volume control, and handling different audio formats.
    Utilizes the pygame library for audio handling to ensure cross-platform compatibility.
    Ensures secure handling of file paths and configurations.
    """

    SUPPORTED_FORMATS = ('.mp3', '.wav', '.ogg', '.flac', '.aac')

    def __init__(self):
        """
        Initializes the MusicPlayerService with necessary configurations and authentication.
        """
        self.logger = setup_logging('MusicPlayerService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.playlist: List[str] = []
        self.current_track_index: int = -1
        self.is_paused: bool = False
        self.volume: float = 0.5  # Default volume
        self._initialize_mixer()
        self.logger.info("MusicPlayerService initialized successfully.")

    def _initialize_mixer(self):
        """
        Initializes the pygame mixer for audio playback.
        """
        try:
            self.logger.debug("Initializing pygame mixer for audio playback.")
            pygame.init()
            mixer.init()
            mixer.music.set_volume(self.volume)
            self.logger.debug("Pygame mixer initialized successfully.")
        except Exception as e:
            self.logger.error(f"Error initializing pygame mixer: {e}", exc_info=True)
            raise MusicPlayerServiceError(f"Error initializing pygame mixer: {e}")

    def load_playlist(self, directory_path: str) -> bool:
        """
        Loads all supported audio files from the specified directory into the playlist.

        Args:
            directory_path (str): The path to the directory containing audio files.

        Returns:
            bool: True if the playlist is loaded successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Loading playlist from directory: {directory_path}.")
            if not os.path.isdir(directory_path):
                self.logger.error(f"Directory '{directory_path}' does not exist.")
                return False

            with self.lock:
                self.playlist = [
                    os.path.join(directory_path, file)
                    for file in os.listdir(directory_path)
                    if file.lower().endswith(self.SUPPORTED_FORMATS)
                ]
                if not self.playlist:
                    self.logger.warning(f"No supported audio files found in '{directory_path}'.")
                    return False
                self.current_track_index = 0
                self.logger.info(f"Playlist loaded with {len(self.playlist)} tracks.")
            return True
        except Exception as e:
            self.logger.error(f"Error loading playlist from '{directory_path}': {e}", exc_info=True)
            return False

    def play(self, track_index: Optional[int] = None) -> bool:
        """
        Plays the specified track or resumes playback if no track index is provided.

        Args:
            track_index (Optional[int], optional): The index of the track to play. Defaults to None.

        Returns:
            bool: True if playback starts successfully, False otherwise.
        """
        try:
            with self.lock:
                if track_index is not None:
                    if 0 <= track_index < len(self.playlist):
                        self.current_track_index = track_index
                        self.logger.debug(f"Playing track index {self.current_track_index}: {self.playlist[self.current_track_index]}.")
                    else:
                        self.logger.error(f"Track index {track_index} is out of range.")
                        return False
                elif self.is_paused:
                    mixer.music.unpause()
                    self.is_paused = False
                    self.logger.info("Resumed playback.")
                    return True
                else:
                    if not self.playlist:
                        self.logger.warning("Playlist is empty. Load a playlist before playing.")
                        return False
                    self.current_track_index = self.current_track_index if self.current_track_index >= 0 else 0
                    self.logger.debug(f"Playing track index {self.current_track_index}: {self.playlist[self.current_track_index]}.")

                mixer.music.load(self.playlist[self.current_track_index])
                mixer.music.play()
                self.logger.info(f"Playback started for '{self.playlist[self.current_track_index]}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error playing track: {e}", exc_info=True)
            return False

    def pause(self) -> bool:
        """
        Pauses the current playback.

        Returns:
            bool: True if playback is paused successfully, False otherwise.
        """
        try:
            with self.lock:
                if mixer.music.get_busy():
                    mixer.music.pause()
                    self.is_paused = True
                    self.logger.info("Playback paused.")
                    return True
                else:
                    self.logger.warning("No track is currently playing to pause.")
                    return False
        except Exception as e:
            self.logger.error(f"Error pausing playback: {e}", exc_info=True)
            return False

    def stop(self) -> bool:
        """
        Stops the current playback.

        Returns:
            bool: True if playback is stopped successfully, False otherwise.
        """
        try:
            with self.lock:
                if mixer.music.get_busy() or self.is_paused:
                    mixer.music.stop()
                    self.is_paused = False
                    self.logger.info("Playback stopped.")
                    return True
                else:
                    self.logger.warning("No track is currently playing to stop.")
                    return False
        except Exception as e:
            self.logger.error(f"Error stopping playback: {e}", exc_info=True)
            return False

    def next_track(self) -> bool:
        """
        Plays the next track in the playlist.

        Returns:
            bool: True if the next track is played successfully, False otherwise.
        """
        try:
            with self.lock:
                if not self.playlist:
                    self.logger.warning("Playlist is empty. Load a playlist before proceeding to the next track.")
                    return False
                self.current_track_index = (self.current_track_index + 1) % len(self.playlist)
                self.logger.debug(f"Moving to next track index {self.current_track_index}: {self.playlist[self.current_track_index]}.")
                mixer.music.load(self.playlist[self.current_track_index])
                mixer.music.play()
                self.logger.info(f"Playback started for '{self.playlist[self.current_track_index]}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error moving to the next track: {e}", exc_info=True)
            return False

    def previous_track(self) -> bool:
        """
        Plays the previous track in the playlist.

        Returns:
            bool: True if the previous track is played successfully, False otherwise.
        """
        try:
            with self.lock:
                if not self.playlist:
                    self.logger.warning("Playlist is empty. Load a playlist before proceeding to the previous track.")
                    return False
                self.current_track_index = (self.current_track_index - 1) % len(self.playlist)
                self.logger.debug(f"Moving to previous track index {self.current_track_index}: {self.playlist[self.current_track_index]}.")
                mixer.music.load(self.playlist[self.current_track_index])
                mixer.music.play()
                self.logger.info(f"Playback started for '{self.playlist[self.current_track_index]}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error moving to the previous track: {e}", exc_info=True)
            return False

    def set_volume(self, volume: float) -> bool:
        """
        Sets the playback volume.

        Args:
            volume (float): The volume level (0.0 to 1.0).

        Returns:
            bool: True if volume is set successfully, False otherwise.
        """
        try:
            if not 0.0 <= volume <= 1.0:
                self.logger.error("Volume must be between 0.0 and 1.0.")
                return False
            with self.lock:
                self.volume = volume
                mixer.music.set_volume(self.volume)
                self.logger.info(f"Volume set to {self.volume * 100}%.")
            return True
        except Exception as e:
            self.logger.error(f"Error setting volume: {e}", exc_info=True)
            return False

    def get_volume(self) -> float:
        """
        Retrieves the current playback volume.

        Returns:
            float: The current volume level (0.0 to 1.0).
        """
        try:
            with self.lock:
                current_volume = mixer.music.get_volume()
            self.logger.debug(f"Current volume is {current_volume * 100}%.")
            return current_volume
        except Exception as e:
            self.logger.error(f"Error retrieving volume: {e}", exc_info=True)
            return self.volume

    def add_track(self, track_path: str) -> bool:
        """
        Adds a single track to the playlist.

        Args:
            track_path (str): The file path of the track to add.

        Returns:
            bool: True if the track is added successfully, False otherwise.
        """
        try:
            if not os.path.isfile(track_path):
                self.logger.error(f"Track file '{track_path}' does not exist.")
                return False
            if not track_path.lower().endswith(self.SUPPORTED_FORMATS):
                self.logger.error(f"Unsupported audio format for file '{track_path}'.")
                return False
            with self.lock:
                self.playlist.append(track_path)
                self.logger.info(f"Track '{track_path}' added to the playlist.")
            return True
        except Exception as e:
            self.logger.error(f"Error adding track '{track_path}': {e}", exc_info=True)
            return False

    def remove_track(self, track_index: int) -> bool:
        """
        Removes a track from the playlist by its index.

        Args:
            track_index (int): The index of the track to remove.

        Returns:
            bool: True if the track is removed successfully, False otherwise.
        """
        try:
            with self.lock:
                if 0 <= track_index < len(self.playlist):
                    removed_track = self.playlist.pop(track_index)
                    self.logger.info(f"Track '{removed_track}' removed from the playlist.")
                    if track_index == self.current_track_index:
                        mixer.music.stop()
                        self.is_paused = False
                        self.current_track_index = -1
                        self.logger.debug("Current track was removed. Playback stopped.")
                    elif track_index < self.current_track_index:
                        self.current_track_index -= 1
                        self.logger.debug(f"Adjusted current track index to {self.current_track_index}.")
                    return True
                else:
                    self.logger.error(f"Track index {track_index} is out of range.")
                    return False
        except Exception as e:
            self.logger.error(f"Error removing track at index {track_index}: {e}", exc_info=True)
            return False

    def shuffle_playlist(self) -> bool:
        """
        Shuffles the current playlist randomly.

        Returns:
            bool: True if the playlist is shuffled successfully, False otherwise.
        """
        try:
            import random
            with self.lock:
                random.shuffle(self.playlist)
                self.current_track_index = 0 if self.playlist else -1
                mixer.music.stop()
                self.is_paused = False
                self.logger.info("Playlist shuffled successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error shuffling playlist: {e}", exc_info=True)
            return False

    def save_playlist(self, file_path: str) -> bool:
        """
        Saves the current playlist to a file.

        Args:
            file_path (str): The file path to save the playlist.

        Returns:
            bool: True if the playlist is saved successfully, False otherwise.
        """
        try:
            import json
            with self.lock:
                with open(file_path, 'w') as f:
                    json.dump(self.playlist, f)
                self.logger.info(f"Playlist saved to '{file_path}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error saving playlist to '{file_path}': {e}", exc_info=True)
            return False

    def load_saved_playlist(self, file_path: str) -> bool:
        """
        Loads a saved playlist from a file.

        Args:
            file_path (str): The file path to load the playlist from.

        Returns:
            bool: True if the playlist is loaded successfully, False otherwise.
        """
        try:
            import json
            if not os.path.isfile(file_path):
                self.logger.error(f"Playlist file '{file_path}' does not exist.")
                return False
            with self.lock:
                with open(file_path, 'r') as f:
                    loaded_playlist = json.load(f)
                if not isinstance(loaded_playlist, list):
                    self.logger.error(f"Invalid playlist format in '{file_path}'.")
                    return False
                self.playlist = loaded_playlist
                self.current_track_index = 0 if self.playlist else -1
                mixer.music.stop()
                self.is_paused = False
                self.logger.info(f"Playlist loaded successfully from '{file_path}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error loading playlist from '{file_path}': {e}", exc_info=True)
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing MusicPlayerService resources.")
            mixer.music.stop()
            mixer.quit()
            pygame.quit()
            self.logger.info("MusicPlayerService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing MusicPlayerService: {e}", exc_info=True)
            raise MusicPlayerServiceError(f"Error closing MusicPlayerService: {e}")
