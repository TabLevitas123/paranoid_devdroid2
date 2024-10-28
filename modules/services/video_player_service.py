# services/video_player_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
import os
import vlc
import time
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager


class VideoPlayerServiceError(Exception):
    """Custom exception for VideoPlayerService-related errors."""
    pass


class VideoPlayerService:
    """
    Provides video playback capabilities, including playing, pausing, stopping videos,
    managing playlists, volume control, fullscreen toggling, and handling different video formats.
    Utilizes the python-vlc library for video handling to ensure cross-platform compatibility.
    Ensures secure handling of file paths and configurations.
    """

    SUPPORTED_FORMATS = ('.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv')

    def __init__(self):
        """
        Initializes the VideoPlayerService with necessary configurations and authentication.
        """
        self.logger = setup_logging('VideoPlayerService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        self.playlist: List[str] = []
        self.current_track_index: int = -1
        self.is_paused: bool = False
        self.volume: int = 50  # Volume range: 0 - 100
        self.player.audio_set_volume(self.volume)
        self.logger.info("VideoPlayerService initialized successfully.")

    def load_playlist(self, directory_path: str) -> bool:
        """
        Loads all supported video files from the specified directory into the playlist.

        Args:
            directory_path (str): The path to the directory containing video files.

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
                    self.logger.warning(f"No supported video files found in '{directory_path}'.")
                    return False
                self.current_track_index = 0
                self.logger.info(f"Playlist loaded with {len(self.playlist)} videos.")
            return True
        except Exception as e:
            self.logger.error(f"Error loading playlist from '{directory_path}': {e}", exc_info=True)
            return False

    def play(self, track_index: Optional[int] = None) -> bool:
        """
        Plays the specified video or resumes playback if no track index is provided.

        Args:
            track_index (Optional[int], optional): The index of the video to play. Defaults to None.

        Returns:
            bool: True if playback starts successfully, False otherwise.
        """
        try:
            with self.lock:
                if track_index is not None:
                    if 0 <= track_index < len(self.playlist):
                        self.current_track_index = track_index
                        self.logger.debug(f"Playing video index {self.current_track_index}: {self.playlist[self.current_track_index]}.")
                    else:
                        self.logger.error(f"Video index {track_index} is out of range.")
                        return False
                elif self.is_paused:
                    self.player.play()
                    self.is_paused = False
                    self.logger.info("Resumed playback.")
                    return True
                else:
                    if not self.playlist:
                        self.logger.warning("Playlist is empty. Load a playlist before playing.")
                        return False
                    self.current_track_index = self.current_track_index if self.current_track_index >= 0 else 0
                    self.logger.debug(f"Playing video index {self.current_track_index}: {self.playlist[self.current_track_index]}.")

                media = self.instance.media_new(self.playlist[self.current_track_index])
                self.player.set_media(media)
                self.player.play()
                self.logger.info(f"Playback started for '{self.playlist[self.current_track_index]}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error playing video: {e}", exc_info=True)
            return False

    def pause(self) -> bool:
        """
        Pauses the current video playback.

        Returns:
            bool: True if playback is paused successfully, False otherwise.
        """
        try:
            with self.lock:
                if self.player.is_playing():
                    self.player.pause()
                    self.is_paused = True
                    self.logger.info("Playback paused.")
                    return True
                else:
                    self.logger.warning("No video is currently playing to pause.")
                    return False
        except Exception as e:
            self.logger.error(f"Error pausing playback: {e}", exc_info=True)
            return False

    def stop(self) -> bool:
        """
        Stops the current video playback.

        Returns:
            bool: True if playback is stopped successfully, False otherwise.
        """
        try:
            with self.lock:
                if self.player.is_playing() or self.is_paused:
                    self.player.stop()
                    self.is_paused = False
                    self.logger.info("Playback stopped.")
                    return True
                else:
                    self.logger.warning("No video is currently playing to stop.")
                    return False
        except Exception as e:
            self.logger.error(f"Error stopping playback: {e}", exc_info=True)
            return False

    def next_video(self) -> bool:
        """
        Plays the next video in the playlist.

        Returns:
            bool: True if the next video is played successfully, False otherwise.
        """
        try:
            with self.lock:
                if not self.playlist:
                    self.logger.warning("Playlist is empty. Load a playlist before proceeding to the next video.")
                    return False
                self.current_track_index = (self.current_track_index + 1) % len(self.playlist)
                self.logger.debug(f"Moving to next video index {self.current_track_index}: {self.playlist[self.current_track_index]}.")
                media = self.instance.media_new(self.playlist[self.current_track_index])
                self.player.set_media(media)
                self.player.play()
                self.logger.info(f"Playback started for '{self.playlist[self.current_track_index]}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error moving to the next video: {e}", exc_info=True)
            return False

    def previous_video(self) -> bool:
        """
        Plays the previous video in the playlist.

        Returns:
            bool: True if the previous video is played successfully, False otherwise.
        """
        try:
            with self.lock:
                if not self.playlist:
                    self.logger.warning("Playlist is empty. Load a playlist before proceeding to the previous video.")
                    return False
                self.current_track_index = (self.current_track_index - 1) % len(self.playlist)
                self.logger.debug(f"Moving to previous video index {self.current_track_index}: {self.playlist[self.current_track_index]}.")
                media = self.instance.media_new(self.playlist[self.current_track_index])
                self.player.set_media(media)
                self.player.play()
                self.logger.info(f"Playback started for '{self.playlist[self.current_track_index]}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error moving to the previous video: {e}", exc_info=True)
            return False

    def set_volume(self, volume: int) -> bool:
        """
        Sets the playback volume.

        Args:
            volume (int): The volume level (0 to 100).

        Returns:
            bool: True if volume is set successfully, False otherwise.
        """
        try:
            if not 0 <= volume <= 100:
                self.logger.error("Volume must be between 0 and 100.")
                return False
            with self.lock:
                self.volume = volume
                self.player.audio_set_volume(self.volume)
                self.logger.info(f"Volume set to {self.volume}%.")
            return True
        except Exception as e:
            self.logger.error(f"Error setting volume: {e}", exc_info=True)
            return False

    def get_volume(self) -> int:
        """
        Retrieves the current playback volume.

        Returns:
            int: The current volume level (0 to 100).
        """
        try:
            with self.lock:
                current_volume = self.player.audio_get_volume()
            self.logger.debug(f"Current volume is {current_volume}%.")
            return current_volume
        except Exception as e:
            self.logger.error(f"Error retrieving volume: {e}", exc_info=True)
            return self.volume

    def toggle_fullscreen(self) -> bool:
        """
        Toggles fullscreen mode for the video player.

        Returns:
            bool: True if fullscreen mode is toggled successfully, False otherwise.
        """
        try:
            with self.lock:
                is_fullscreen = self.player.get_fullscreen()
                self.player.set_fullscreen(not is_fullscreen)
                self.logger.info(f"Fullscreen mode {'enabled' if not is_fullscreen else 'disabled'}.")
            return True
        except Exception as e:
            self.logger.error(f"Error toggling fullscreen mode: {e}", exc_info=True)
            return False

    def add_video(self, video_path: str) -> bool:
        """
        Adds a single video to the playlist.

        Args:
            video_path (str): The file path of the video to add.

        Returns:
            bool: True if the video is added successfully, False otherwise.
        """
        try:
            if not os.path.isfile(video_path):
                self.logger.error(f"Video file '{video_path}' does not exist.")
                return False
            if not video_path.lower().endswith(self.SUPPORTED_FORMATS):
                self.logger.error(f"Unsupported video format for file '{video_path}'.")
                return False
            with self.lock:
                self.playlist.append(video_path)
                self.logger.info(f"Video '{video_path}' added to the playlist.")
            return True
        except Exception as e:
            self.logger.error(f"Error adding video '{video_path}': {e}", exc_info=True)
            return False

    def remove_video(self, video_index: int) -> bool:
        """
        Removes a video from the playlist by its index.

        Args:
            video_index (int): The index of the video to remove.

        Returns:
            bool: True if the video is removed successfully, False otherwise.
        """
        try:
            with self.lock:
                if 0 <= video_index < len(self.playlist):
                    removed_video = self.playlist.pop(video_index)
                    self.logger.info(f"Video '{removed_video}' removed from the playlist.")
                    if video_index == self.current_track_index:
                        self.player.stop()
                        self.is_paused = False
                        self.current_track_index = -1
                        self.logger.debug("Current video was removed. Playback stopped.")
                    elif video_index < self.current_track_index:
                        self.current_track_index -= 1
                        self.logger.debug(f"Adjusted current video index to {self.current_track_index}.")
                    return True
                else:
                    self.logger.error(f"Video index {video_index} is out of range.")
                    return False
        except Exception as e:
            self.logger.error(f"Error removing video at index {video_index}: {e}", exc_info=True)
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
                self.player.stop()
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
                self.player.stop()
                self.is_paused = False
                self.logger.info(f"Playlist loaded successfully from '{file_path}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error loading playlist from '{file_path}': {e}", exc_info=True)
            return False

    def get_current_track(self) -> Optional[str]:
        """
        Retrieves the path of the currently playing track.

        Returns:
            Optional[str]: The current track path, or None if no track is playing.
        """
        try:
            with self.lock:
                if 0 <= self.current_track_index < len(self.playlist):
                    current_track = self.playlist[self.current_track_index]
                    self.logger.debug(f"Current track: {current_track}.")
                    return current_track
                else:
                    self.logger.debug("No track is currently playing.")
                    return None
        except Exception as e:
            self.logger.error(f"Error retrieving current track: {e}", exc_info=True)
            return None

    def get_playlist(self) -> List[str]:
        """
        Retrieves the current playlist.

        Returns:
            List[str]: The list of video paths in the playlist.
        """
        try:
            with self.lock:
                self.logger.debug(f"Current playlist: {self.playlist}.")
                return list(self.playlist)
        except Exception as e:
            self.logger.error(f"Error retrieving playlist: {e}", exc_info=True)
            return []

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing VideoPlayerService resources.")
            self.player.stop()
            self.logger.info("VideoPlayerService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing VideoPlayerService: {e}", exc_info=True)
            raise VideoPlayerServiceError(f"Error closing VideoPlayerService: {e}")
