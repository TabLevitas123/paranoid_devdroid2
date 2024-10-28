# services/text_to_speech_service.py

import logging
import threading
import os
from typing import Any, Dict, List, Optional
from pydub import AudioSegment
from pydub.playback import play
from gtts import gTTS
import tempfile
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

class TextToSpeechServiceError(Exception):
    """Custom exception for TextToSpeechService-related errors."""
    pass

class TextToSpeechService:
    """
    Provides text-to-speech (TTS) capabilities, converting text inputs into spoken audio.
    Utilizes the Google Text-to-Speech (gTTS) library and supports multiple languages and voices.
    Ensures secure handling of API keys and configurations.
    """

    def __init__(self):
        """
        Initializes the TextToSpeechService with necessary configurations and authentication.
        """
        self.logger = setup_logging('TextToSpeechService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.supported_languages = self._load_supported_languages()
        self.default_language = self.config_loader.get('TTS_DEFAULT_LANGUAGE', 'en')
        self.default_voice = self.config_loader.get('TTS_DEFAULT_VOICE', 'male')
        self.cache_dir = self.config_loader.get('TTS_CACHE_DIR', './tts_cache')
        self._initialize_cache()
        self.lock = threading.Lock()
        self.logger.info("TextToSpeechService initialized successfully.")

    def _load_supported_languages(self) -> Dict[str, str]:
        """
        Loads supported language codes and their corresponding language names.

        Returns:
            Dict[str, str]: A dictionary mapping language codes to language names.
        """
        try:
            self.logger.debug("Loading supported languages from configuration.")
            languages = self.config_loader.get('SUPPORTED_TTS_LANGUAGES', {})
            self.logger.debug(f"Supported TTS languages loaded: {languages}")
            return languages
        except Exception as e:
            self.logger.error(f"Error loading supported languages: {e}", exc_info=True)
            raise TextToSpeechServiceError(f"Error loading supported languages: {e}")

    def _initialize_cache(self):
        """
        Initializes the cache directory for storing generated audio files.
        """
        try:
            self.logger.debug(f"Initializing TTS cache directory at '{self.cache_dir}'.")
            os.makedirs(self.cache_dir, exist_ok=True)
            self.logger.debug("TTS cache directory initialized successfully.")
        except Exception as e:
            self.logger.error(f"Error initializing cache directory: {e}", exc_info=True)
            raise TextToSpeechServiceError(f"Error initializing cache directory: {e}")

    def _get_cached_audio_path(self, text: str, language: str, voice: str) -> str:
        """
        Generates a unique file path for the cached audio based on the input parameters.

        Args:
            text (str): The text to convert to speech.
            language (str): The language code.
            voice (str): The voice type ('male' or 'female').

        Returns:
            str: The file path to the cached audio.
        """
        import hashlib

        hash_input = f"{text}_{language}_{voice}".encode('utf-8')
        hash_digest = hashlib.md5(hash_input).hexdigest()
        file_path = os.path.join(self.cache_dir, f"{hash_digest}.mp3")
        self.logger.debug(f"Generated cached audio path: {file_path}")
        return file_path

    def _synthesize_speech(self, text: str, language: str, voice: str) -> Optional[str]:
        """
        Synthesizes speech from text using gTTS and saves it to the cache directory.

        Args:
            text (str): The text to convert to speech.
            language (str): The language code.
            voice (str): The voice type ('male' or 'female').

        Returns:
            Optional[str]: The file path to the synthesized audio, or None if synthesis fails.
        """
        try:
            self.logger.debug(f"Synthesizing speech for text: '{text}' with language: '{language}' and voice: '{voice}'")
            tts = gTTS(text=text, lang=language, slow=False)
            cached_path = self._get_cached_audio_path(text, language, voice)
            tts.save(cached_path)
            self.logger.info(f"Speech synthesized and saved to '{cached_path}' successfully.")
            return cached_path
        except Exception as e:
            self.logger.error(f"Error synthesizing speech: {e}", exc_info=True)
            return None

    def _play_audio(self, audio_path: str):
        """
        Plays the audio file using pydub.

        Args:
            audio_path (str): The file path to the audio file.
        """
        try:
            self.logger.debug(f"Playing audio from '{audio_path}'.")
            audio = AudioSegment.from_mp3(audio_path)
            play(audio)
            self.logger.info(f"Audio played successfully from '{audio_path}'.")
        except Exception as e:
            self.logger.error(f"Error playing audio '{audio_path}': {e}", exc_info=True)

    def convert_text_to_speech(self, text: str, language: Optional[str] = None, voice: Optional[str] = None, play: bool = False) -> Optional[str]:
        """
        Converts text to speech, optionally playing the audio.

        Args:
            text (str): The text to convert to speech.
            language (Optional[str], optional): The language code. Defaults to the service's default language.
            voice (Optional[str], optional): The voice type ('male' or 'female'). Defaults to the service's default voice.
            play (bool, optional): Whether to play the audio after synthesis. Defaults to False.

        Returns:
            Optional[str]: The file path to the synthesized audio, or None if conversion fails.
        """
        language = language or self.default_language
        voice = voice or self.default_voice

        if language not in self.supported_languages:
            self.logger.error(f"Unsupported language code '{language}'. Supported languages: {list(self.supported_languages.keys())}")
            return None

        if voice not in ['male', 'female']:
            self.logger.error(f"Unsupported voice type '{voice}'. Supported voices: 'male', 'female'")
            return None

        cached_path = self._get_cached_audio_path(text, language, voice)
        if os.path.exists(cached_path):
            self.logger.debug(f"Audio found in cache at '{cached_path}'.")
        else:
            cached_path = self._synthesize_speech(text, language, voice)
            if not cached_path:
                return None

        if play:
            self._play_audio(cached_path)

        return cached_path

    def batch_convert_text_to_speech(self, texts: List[str], language: Optional[str] = None, voice: Optional[str] = None, play: bool = False) -> List[Optional[str]]:
        """
        Converts a batch of texts to speech.

        Args:
            texts (List[str]): A list of texts to convert to speech.
            language (Optional[str], optional): The language code. Defaults to the service's default language.
            voice (Optional[str], optional): The voice type ('male' or 'female'). Defaults to the service's default voice.
            play (bool, optional): Whether to play each audio after synthesis. Defaults to False.

        Returns:
            List[Optional[str]]: A list of file paths to the synthesized audios.
        """
        results = []
        for text in texts:
            result = self.convert_text_to_speech(text, language, voice, play)
            results.append(result)
        return results

    def convert_text_to_speech_async(self, text: str, language: Optional[str] = None, voice: Optional[str] = None, play: bool = False, callback: Optional[Any] = None) -> threading.Thread:
        """
        Converts text to speech asynchronously and optionally executes a callback with the result.

        Args:
            text (str): The text to convert to speech.
            language (Optional[str], optional): The language code. Defaults to the service's default language.
            voice (Optional[str], optional): The voice type ('male' or 'female'). Defaults to the service's default voice.
            play (bool, optional): Whether to play the audio after synthesis. Defaults to False.
            callback (Optional[Any], optional): A callback function to execute with the synthesized audio path. Defaults to None.

        Returns:
            threading.Thread: The thread handling the asynchronous conversion.
        """
        def convert():
            try:
                self.logger.debug("Starting asynchronous text-to-speech conversion.")
                audio_path = self.convert_text_to_speech(text, language, voice, play)
                if callback and callable(callback):
                    callback(audio_path)
                self.logger.debug("Asynchronous text-to-speech conversion completed.")
            except Exception as e:
                self.logger.error(f"Error in asynchronous text-to-speech conversion: {e}", exc_info=True)

        thread = threading.Thread(target=convert, daemon=True)
        thread.start()
        self.logger.info("Scheduled asynchronous text-to-speech conversion.")
        return thread

    def get_supported_languages(self) -> Dict[str, str]:
        """
        Retrieves the list of supported languages for text-to-speech.

        Returns:
            Dict[str, str]: A dictionary mapping language codes to language names.
        """
        try:
            self.logger.debug("Retrieving supported languages.")
            return self.supported_languages
        except Exception as e:
            self.logger.error(f"Error retrieving supported languages: {e}", exc_info=True)
            return {}

    def add_supported_language(self, lang_code: str, lang_name: str) -> bool:
        """
        Adds a new language to the list of supported languages.

        Args:
            lang_code (str): The language code.
            lang_name (str): The language name.

        Returns:
            bool: True if the language is added successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Adding supported language '{lang_code}': '{lang_name}'.")
            self.supported_languages[lang_code] = lang_name
            self.logger.info(f"Supported language '{lang_code}': '{lang_name}' added successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error adding supported language '{lang_code}': {e}", exc_info=True)
            return False

    def remove_supported_language(self, lang_code: str) -> bool:
        """
        Removes a language from the list of supported languages.

        Args:
            lang_code (str): The language code to remove.

        Returns:
            bool: True if the language is removed successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Removing supported language '{lang_code}'.")
            if lang_code in self.supported_languages:
                del self.supported_languages[lang_code]
                self.logger.info(f"Supported language '{lang_code}' removed successfully.")
                return True
            else:
                self.logger.warning(f"Supported language '{lang_code}' does not exist.")
                return False
        except Exception as e:
            self.logger.error(f"Error removing supported language '{lang_code}': {e}", exc_info=True)
            return False

    def clear_cache(self) -> bool:
        """
        Clears the TTS cache by deleting all cached audio files.

        Returns:
            bool: True if the cache is cleared successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Clearing TTS cache at '{self.cache_dir}'.")
            for filename in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    self.logger.debug(f"Deleted cached audio file '{file_path}'.")
            self.logger.info("TTS cache cleared successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error clearing TTS cache: {e}", exc_info=True)
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing TextToSpeechService resources.")
            # Currently, no persistent resources to close
            self.logger.info("TextToSpeechService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing TextToSpeechService: {e}", exc_info=True)
            raise TextToSpeechServiceError(f"Error closing TextToSpeechService: {e}")
