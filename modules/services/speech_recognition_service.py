# services/speech_recognition_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
import speech_recognition_service as sr
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

class SpeechRecognitionServiceError(Exception):
    """Custom exception for SpeechRecognitionService-related errors."""
    pass

class SpeechRecognitionService:
    """
    Provides speech recognition capabilities, converting audio inputs into text.
    Utilizes the SpeechRecognition library with support for various speech recognition engines.
    Ensures secure and efficient processing of audio data.
    """

    def __init__(self):
        """
        Initializes the SpeechRecognitionService with necessary configurations and recognizer setup.
        """
        self.logger = setup_logging('SpeechRecognitionService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.recognition_engine = self.config_loader.get('SPEECH_RECOGNITION_ENGINE', 'google')
        self.api_key = self._load_api_key()
        self.lock = threading.Lock()
        self.logger.info("SpeechRecognitionService initialized successfully.")

    def _load_api_key(self) -> Optional[str]:
        """
        Loads and decrypts the API key for the speech recognition engine if required.

        Returns:
            Optional[str]: The decrypted API key, or None if not required.
        """
        try:
            self.logger.debug("Loading speech recognition engine API key from configuration.")
            encrypted_key = self.config_loader.get('SPEECH_RECOGNITION_API_KEY_ENCRYPTED')
            if encrypted_key:
                decrypted_key = self.encryption_manager.decrypt_data(encrypted_key).decode('utf-8')
                self.logger.debug("Speech recognition API key decrypted successfully.")
                return decrypted_key
            else:
                self.logger.debug("No API key found for speech recognition engine.")
                return None
        except Exception as e:
            self.logger.error(f"Error loading speech recognition API key: {e}", exc_info=True)
            raise SpeechRecognitionServiceError(f"Error loading speech recognition API key: {e}")

    def transcribe_audio_file(self, audio_path: str, language: str = "en-US") -> Optional[str]:
        """
        Transcribes an audio file into text using the specified recognition engine.

        Args:
            audio_path (str): The file path to the audio file to transcribe.
            language (str, optional): The language of the audio. Defaults to "en-US".

        Returns:
            Optional[str]: The transcribed text, or None if transcription fails.
        """
        try:
            self.logger.debug(f"Transcribing audio file: {audio_path} with language: {language}")
            with sr.AudioFile(audio_path) as source:
                with self.lock:
                    audio = self.recognizer.record(source)
            with self.lock:
                if self.recognition_engine.lower() == 'google':
                    transcription = self.recognizer.recognize_google(audio, language=language)
                elif self.recognition_engine.lower() == 'sphinx':
                    transcription = self.recognizer.recognize_sphinx(audio, language=language)
                elif self.recognition_engine.lower() == 'bing':
                    if not self.api_key:
                        self.logger.error("Bing Speech API key is not configured.")
                        return None
                    transcription = self.recognizer.recognize_bing(audio, key=self.api_key, language=language)
                else:
                    self.logger.error(f"Unsupported recognition engine '{self.recognition_engine}'.")
                    return None
            self.logger.info(f"Transcription successful: {transcription}")
            return transcription
        except sr.UnknownValueError:
            self.logger.warning(f"SpeechRecognition could not understand audio from '{audio_path}'.")
            return None
        except sr.RequestError as e:
            self.logger.error(f"Could not request results from {self.recognition_engine} service; {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Error transcribing audio file '{audio_path}': {e}", exc_info=True)
            return None

    def transcribe_microphone_input(self, duration: int = 5, language: str = "en-US") -> Optional[str]:
        """
        Transcribes speech from the microphone input.

        Args:
            duration (int, optional): Duration in seconds to listen for audio. Defaults to 5.
            language (str, optional): The language of the speech. Defaults to "en-US".

        Returns:
            Optional[str]: The transcribed text, or None if transcription fails.
        """
        try:
            self.logger.debug(f"Starting microphone transcription for duration: {duration} seconds with language: {language}")
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source)
                audio = self.recognizer.listen(source, duration=duration)
            with self.lock:
                if self.recognition_engine.lower() == 'google':
                    transcription = self.recognizer.recognize_google(audio, language=language)
                elif self.recognition_engine.lower() == 'sphinx':
                    transcription = self.recognizer.recognize_sphinx(audio, language=language)
                elif self.recognition_engine.lower() == 'bing':
                    if not self.api_key:
                        self.logger.error("Bing Speech API key is not configured.")
                        return None
                    transcription = self.recognizer.recognize_bing(audio, key=self.api_key, language=language)
                else:
                    self.logger.error(f"Unsupported recognition engine '{self.recognition_engine}'.")
                    return None
            self.logger.info(f"Microphone transcription successful: {transcription}")
            return transcription
        except sr.UnknownValueError:
            self.logger.warning("SpeechRecognition could not understand microphone input.")
            return None
        except sr.RequestError as e:
            self.logger.error(f"Could not request results from {self.recognition_engine} service; {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Error transcribing microphone input: {e}", exc_info=True)
            return None

    def batch_transcribe_audio_files(self, audio_paths: List[str], language: str = "en-US") -> List[Optional[str]]:
        """
        Transcribes multiple audio files in a batch.

        Args:
            audio_paths (List[str]): A list of file paths to audio files to transcribe.
            language (str, optional): The language of the audio. Defaults to "en-US".

        Returns:
            List[Optional[str]]: A list of transcriptions corresponding to each audio file.
        """
        results = []
        for path in audio_paths:
            transcription = self.transcribe_audio_file(path, language)
            results.append(transcription)
        return results

    def transcribe_audio_async(self, audio_path: str, language: str = "en-US", callback: Optional[Any] = None) -> threading.Thread:
        """
        Transcribes an audio file asynchronously and optionally executes a callback with the result.

        Args:
            audio_path (str): The file path to the audio file to transcribe.
            language (str, optional): The language of the audio. Defaults to "en-US".
            callback (Optional[Any], optional): A callback function to execute with the transcription. Defaults to None.

        Returns:
            threading.Thread: The thread handling the asynchronous transcription.
        """
        def transcribe():
            try:
                self.logger.debug("Starting asynchronous transcription.")
                transcription = self.transcribe_audio_file(audio_path, language)
                if callback and callable(callback):
                    callback(transcription)
                self.logger.debug("Asynchronous transcription completed.")
            except Exception as e:
                self.logger.error(f"Error in asynchronous transcription: {e}", exc_info=True)

        thread = threading.Thread(target=transcribe, daemon=True)
        thread.start()
        self.logger.info(f"Scheduled asynchronous transcription for '{audio_path}'.")
        return thread

    def transcribe_microphone_async(self, duration: int = 5, language: str = "en-US", callback: Optional[Any] = None) -> threading.Thread:
        """
        Transcribes microphone input asynchronously and optionally executes a callback with the result.

        Args:
            duration (int, optional): Duration in seconds to listen for audio. Defaults to 5.
            language (str, optional): The language of the speech. Defaults to "en-US".
            callback (Optional[Any], optional): A callback function to execute with the transcription. Defaults to None.

        Returns:
            threading.Thread: The thread handling the asynchronous microphone transcription.
        """
        def transcribe():
            try:
                self.logger.debug("Starting asynchronous microphone transcription.")
                transcription = self.transcribe_microphone_input(duration, language)
                if callback and callable(callback):
                    callback(transcription)
                self.logger.debug("Asynchronous microphone transcription completed.")
            except Exception as e:
                self.logger.error(f"Error in asynchronous microphone transcription: {e}", exc_info=True)

        thread = threading.Thread(target=transcribe, daemon=True)
        thread.start()
        self.logger.info("Scheduled asynchronous microphone transcription.")
        return thread

    def get_recognition_engine(self) -> str:
        """
        Retrieves the current speech recognition engine being used.

        Returns:
            str: The name of the recognition engine.
        """
        try:
            self.logger.debug("Retrieving current recognition engine.")
            return self.recognition_engine
        except Exception as e:
            self.logger.error(f"Error retrieving recognition engine: {e}", exc_info=True)
            return "Unknown"

    def set_recognition_engine(self, engine_name: str) -> bool:
        """
        Sets the speech recognition engine to be used.

        Args:
            engine_name (str): The name of the recognition engine ('google', 'sphinx', 'bing').

        Returns:
            bool: True if the engine is set successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Setting recognition engine to '{engine_name}'.")
            supported_engines = ['google', 'sphinx', 'bing']
            if engine_name.lower() not in supported_engines:
                self.logger.error(f"Unsupported recognition engine '{engine_name}'. Supported engines: {supported_engines}")
                return False
            self.recognition_engine = engine_name.lower()
            self.logger.info(f"Recognition engine set to '{self.recognition_engine}' successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error setting recognition engine to '{engine_name}': {e}", exc_info=True)
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing SpeechRecognitionService resources.")
            # Placeholder for any cleanup operations if necessary
            self.logger.info("SpeechRecognitionService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing SpeechRecognitionService: {e}", exc_info=True)
            raise SpeechRecognitionServiceError(f"Error closing SpeechRecognitionService: {e}")
