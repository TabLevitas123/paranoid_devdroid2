# services/translation_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
import requests
from transformers import MarianMTModel, MarianTokenizer
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

class TranslationServiceError(Exception):
    """Custom exception for TranslationService-related errors."""
    pass

class TranslationService:
    """
    Provides translation capabilities using pre-trained transformer models.
    Handles text translation, language detection, and ensures secure and efficient operations.
    """

    def __init__(self):
        """
        Initializes the TranslationService with necessary configurations and model setup.
        """
        self.logger = setup_logging('TranslationService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.supported_languages = self._load_supported_languages()
        self.model_name = self.config_loader.get('TRANSLATION_MODEL_NAME', 'Helsinki-NLP/opus-mt-en-de')
        self.tokenizer, self.model = self._initialize_model()
        self.lock = threading.Lock()
        self.logger.info("TranslationService initialized successfully.")

    def _load_supported_languages(self) -> Dict[str, str]:
        """
        Loads supported language codes and their corresponding language names.

        Returns:
            Dict[str, str]: A dictionary mapping language codes to language names.
        """
        try:
            self.logger.debug("Loading supported languages from configuration.")
            languages = self.config_loader.get('SUPPORTED_LANGUAGES', {})
            self.logger.debug(f"Supported languages loaded: {languages}")
            return languages
        except Exception as e:
            self.logger.error(f"Error loading supported languages: {e}", exc_info=True)
            raise TranslationServiceError(f"Error loading supported languages: {e}")

    def _initialize_model(self) -> List[MarianMTModel, MarianTokenizer]:
        """
        Initializes the MarianMT model and tokenizer for translation.

        Returns:
            (MarianTokenizer, MarianMTModel): The tokenizer and model instances.

        Raises:
            TranslationServiceError: If the model fails to load.
        """
        try:
            self.logger.debug(f"Loading translation model '{self.model_name}'.")
            tokenizer = MarianTokenizer.from_pretrained(self.model_name)
            model = MarianMTModel.from_pretrained(self.model_name)
            self.logger.debug("Translation model and tokenizer loaded successfully.")
            return tokenizer, model
        except Exception as e:
            self.logger.error(f"Error initializing translation model: {e}", exc_info=True)
            raise TranslationServiceError(f"Error initializing translation model: {e}")

    def translate_text(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """
        Translates a single text from the source language to the target language.

        Args:
            text (str): The text to translate.
            source_lang (str): The language code of the source text.
            target_lang (str): The language code to translate the text into.

        Returns:
            Optional[str]: The translated text, or None if translation fails.
        """
        try:
            self.logger.debug(f"Translating text from '{source_lang}' to '{target_lang}': {text}")
            if source_lang not in self.supported_languages or target_lang not in self.supported_languages:
                self.logger.error(f"Unsupported language codes: {source_lang} -> {target_lang}")
                return None

            # Load the appropriate model if target language changes
            model_name = f'Helsinki-NLP/opus-mt-{source_lang}-{target_lang}'
            if model_name != self.model_name:
                self.logger.debug(f"Switching to translation model '{model_name}'.")
                self.tokenizer = MarianTokenizer.from_pretrained(model_name)
                self.model = MarianMTModel.from_pretrained(model_name)
                self.model_name = model_name

            with self.lock:
                translated = self.model.generate(**self.tokenizer.prepare_seq2seq_batch([text], return_tensors="pt"))
                translated_text = self.tokenizer.decode(translated[0], skip_special_tokens=True)
            self.logger.info(f"Translation successful: {translated_text}")
            return translated_text
        except Exception as e:
            self.logger.error(f"Error translating text: {e}", exc_info=True)
            return None

    def batch_translate_texts(self, texts: List[str], source_lang: str, target_lang: str) -> List[Optional[str]]:
        """
        Translates a batch of texts from the source language to the target language.

        Args:
            texts (List[str]): A list of texts to translate.
            source_lang (str): The language code of the source texts.
            target_lang (str): The language code to translate the texts into.

        Returns:
            List[Optional[str]]: A list of translated texts corresponding to each input text.
        """
        results = []
        for text in texts:
            translated = self.translate_text(text, source_lang, target_lang)
            results.append(translated)
        return results

    def detect_language(self, text: str) -> Optional[str]:
        """
        Detects the language of a given text using an external API.

        Args:
            text (str): The text whose language needs to be detected.

        Returns:
            Optional[str]: The detected language code, or None if detection fails.
        """
        try:
            self.logger.debug(f"Detecting language for text: {text}")
            api_url = self.config_loader.get('LANGUAGE_DETECTION_API_URL', 'https://libretranslate.de/detect')
            payload = {'q': text}
            headers = {'Content-Type': 'application/json'}
            response = requests.post(api_url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            detections = response.json()
            if detections:
                detected_lang = detections[0]['language']
                self.logger.info(f"Detected language: {detected_lang}")
                return detected_lang
            else:
                self.logger.warning("No language detected.")
                return None
        except Exception as e:
            self.logger.error(f"Error detecting language: {e}", exc_info=True)
            return None

    def translate_text_async(self, text: str, source_lang: str, target_lang: str, callback: Optional[Any] = None) -> threading.Thread:
        """
        Translates text asynchronously and optionally executes a callback with the result.

        Args:
            text (str): The text to translate.
            source_lang (str): The language code of the source text.
            target_lang (str): The language code to translate the text into.
            callback (Optional[Any], optional): A callback function to execute with the translated text. Defaults to None.

        Returns:
            threading.Thread: The thread handling the asynchronous translation.
        """
        def translate():
            try:
                self.logger.debug("Starting asynchronous translation.")
                translated_text = self.translate_text(text, source_lang, target_lang)
                if callback and callable(callback):
                    callback(translated_text)
                self.logger.debug("Asynchronous translation completed.")
            except Exception as e:
                self.logger.error(f"Error in asynchronous translation: {e}", exc_info=True)

        thread = threading.Thread(target=translate, daemon=True)
        thread.start()
        self.logger.info("Scheduled asynchronous translation.")
        return thread

    def translate_batch_async(self, texts: List[str], source_lang: str, target_lang: str, callback: Optional[Any] = None) -> threading.Thread:
        """
        Translates a batch of texts asynchronously and optionally executes a callback with the results.

        Args:
            texts (List[str]): A list of texts to translate.
            source_lang (str): The language code of the source texts.
            target_lang (str): The language code to translate the texts into.
            callback (Optional[Any], optional): A callback function to execute with the translated texts. Defaults to None.

        Returns:
            threading.Thread: The thread handling the asynchronous batch translation.
        """
        def translate_batch():
            try:
                self.logger.debug("Starting asynchronous batch translation.")
                translated_texts = self.batch_translate_texts(texts, source_lang, target_lang)
                if callback and callable(callback):
                    callback(translated_texts)
                self.logger.debug("Asynchronous batch translation completed.")
            except Exception as e:
                self.logger.error(f"Error in asynchronous batch translation: {e}", exc_info=True)

        thread = threading.Thread(target=translate_batch, daemon=True)
        thread.start()
        self.logger.info("Scheduled asynchronous batch translation.")
        return thread

    def get_supported_languages(self) -> Dict[str, str]:
        """
        Retrieves the list of supported languages for translation.

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

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing TranslationService resources.")
            # Placeholder for any cleanup operations if necessary
            self.logger.info("TranslationService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing TranslationService: {e}", exc_info=True)
            raise TranslationServiceError(f"Error closing TranslationService: {e}")
