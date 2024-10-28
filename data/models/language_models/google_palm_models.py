# language_models/google_palm_models.py

import logging
from typing import Any, Dict, Optional, List

import requests
from requests.exceptions import RequestException

from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from databases.vector_db import VectorDatabase, VectorDatabaseError
from shared_memory.shared_data_structures import SharedMemoryManager
from databases.time_series_db import TimeSeriesDatabase


class GooglePaLMModelsError(Exception):
    """Custom exception for GooglePaLMModels-related errors."""
    pass


class GooglePaLMModels:
    """
    Manages interactions with Google's PaLM language models.
    Provides methods to generate text, list available models, and handle model-specific operations.
    Integrates with VectorDatabase, SharedMemoryManager, and TimeSeriesDatabase for enhanced functionalities.
    """

    def __init__(self):
        """
        Initializes the GooglePaLMModels with necessary configurations, authentication, and integrations.
        """
        # Setup logging
        self.logger = setup_logging('GooglePaLMModels')

        # Load configurations
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()

        # Initialize integrations
        try:
            self.vector_db = VectorDatabase()
            self.shared_memory = SharedMemoryManager(name='llm_shared_memory', size=1024 * 1024 * 200)  # 200 MB
            self.time_series_db = TimeSeriesDatabase()
            self.logger.info("Integrated with VectorDatabase, SharedMemoryManager, and TimeSeriesDatabase successfully.")
        except Exception as e:
            self.logger.error(f"Failed to integrate with other systems: {e}", exc_info=True)
            raise GooglePaLMModelsError(f"Failed to integrate with other systems: {e}")

        # Initialize Google PaLM API configurations
        try:
            self.api_key_encrypted = self.config_loader.get('GOOGLE_PALM_API_KEY_ENCRYPTED')
            self.project_id_encrypted = self.config_loader.get('GOOGLE_PALM_PROJECT_ID_ENCRYPTED')
            self.api_endpoint = self.config_loader.get('GOOGLE_PALM_API_ENDPOINT', 'https://generativelanguage.googleapis.com/v1beta2/models')
    
            if not all([self.api_key_encrypted, self.project_id_encrypted]):
                self.logger.error("Google PaLM API key or Project ID is missing in configurations.")
                raise GooglePaLMModelsError("Google PaLM API key or Project ID is missing in configurations.")
    
            self.api_key = self.encryption_manager.decrypt_data(self.api_key_encrypted).decode('utf-8')
            self.project_id = self.encryption_manager.decrypt_data(self.project_id_encrypted).decode('utf-8')
            self.logger.info("Google PaLM API key and Project ID set successfully.")
    
            # Prepare authorization headers
            self.headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
        except Exception as e:
            self.logger.error(f"Failed to initialize Google PaLM API configurations: {e}", exc_info=True)
            raise GooglePaLMModelsError(f"Failed to initialize Google PaLM API configurations: {e}")

        # Initialize model list
        try:
            self.available_models = self.list_models()
            self.logger.info(f"Retrieved {len(self.available_models)} Google PaLM models.")
        except Exception as e:
            self.logger.error(f"Failed to retrieve Google PaLM models: {e}", exc_info=True)
            raise GooglePaLMModelsError(f"Failed to retrieve Google PaLM models: {e}")

    def list_models(self) -> List[str]:
        """
        Retrieves a list of all available Google PaLM models.
    
        Returns:
            List[str]: A list of model IDs.
        """
        try:
            url = f"{self.api_endpoint}"
            params = {'key': self.api_key}
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            models = [model['name'] for model in data.get('models', [])]
            self.logger.debug(f"Retrieved models: {models}")
            return models
        except RequestException as e:
            self.logger.error(f"HTTP error while listing Google PaLM models: {e}", exc_info=True)
            raise GooglePaLMModelsError(f"HTTP error while listing Google PaLM models: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while listing Google PaLM models: {e}", exc_info=True)
            raise GooglePaLMModelsError(f"Unexpected error while listing Google PaLM models: {e}")

    def generate_text(
        self,
        prompt: str,
        model: str = "models/text-bison-001",
        max_tokens: int = 150,
        temperature: float = 0.7,
        top_p: float = 1.0,
        n: int = 1,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Generates text using the specified Google PaLM model.
    
        Args:
            prompt (str): The input text prompt for the model.
            model (str, optional): The Google PaLM model to use. Defaults to "models/text-bison-001".
            max_tokens (int, optional): The maximum number of tokens to generate. Defaults to 150.
            temperature (float, optional): Sampling temperature. Defaults to 0.7.
            top_p (float, optional): Top-p sampling probability. Defaults to 1.0.
            n (int, optional): Number of completions to generate. Defaults to 1.
            stop (Optional[List[str]], optional): Stop sequences. Defaults to None.
            **kwargs: Additional parameters for Google PaLM API.
    
        Returns:
            Optional[List[Dict[str, Any]]]: A list of generated text completions if successful, else None.
        """
        try:
            # Validate model
            if model not in self.available_models:
                self.logger.error(f"Model '{model}' is not available in Google PaLM models.")
                return None

            # Check if result is cached
            cache_key = f"google_palm_{model}_{hash(prompt)}_{max_tokens}_{temperature}_{top_p}_{n}"
            cached_result = self.shared_memory.get_data(key=cache_key)
            if cached_result:
                self.logger.info(f"Retrieved cached result for key '{cache_key}'.")
                return cached_result

            # Prepare request payload
            payload = {
                "prompt": prompt,
                "maxTokens": max_tokens,
                "temperature": temperature,
                "topP": top_p,
                "n": n,
                "stopSequences": stop,
                **kwargs
            }

            # Make API request
            self.logger.info(f"Generating text with model '{model}' for prompt: {prompt}")
            url = f"{self.api_endpoint}/{model}:generateText?key={self.api_key}"
            response = requests.post(url, headers=self.headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()

            # Extract completions
            completions = []
            for choice in data.get('candidates', []):
                completion = {
                    "text": choice.get('output', ''),
                    "index": choice.get('index', 0),
                    "logprobs": choice.get('logprobs', {}),
                    "finish_reason": choice.get('finishReason', 'unknown')
                }
                completions.append(completion)
            self.logger.debug(f"Generated completions: {completions}")

            # Cache the result
            self.shared_memory.cache_data(key=cache_key, value=completions)
            self.logger.debug(f"Cached result with key '{cache_key}'.")

            # Log the generation event
            self.time_series_db.log_event(
                event_type='google_palm_text_generation',
                details={
                    'model': model,
                    'prompt': prompt,
                    'max_tokens': max_tokens,
                    'temperature': temperature,
                    'top_p': top_p,
                    'n': n,
                    'stop_sequences': stop,
                    'completions_count': len(completions)
                }
            )

            return completions
        except RequestException as e:
            self.logger.error(f"HTTP error during text generation with Google PaLM: {e}", exc_info=True)
            return None
        except GooglePaLMModelsError as e:
            self.logger.error(f"Google PaLM API error during text generation: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during text generation with Google PaLM: {e}", exc_info=True)
            return None

    def dispose(self):
        """
        Disposes of all resources and integrations.
        """
        try:
            self.close()
        except GooglePaLMModelsError as e:
            self.logger.error(f"Error during disposal: {e}", exc_info=True)
            raise

    def close(self):
        """
        Closes all integrations and releases resources.
        """
        try:
            # Close SharedMemoryManager
            self.shared_memory.close()
            self.logger.info("SharedMemoryManager closed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to close SharedMemoryManager: {e}", exc_info=True)
            raise GooglePaLMModelsError(f"Failed to close SharedMemoryManager: {e}")

        try:
            # Close TimeSeriesDatabase
            self.time_series_db.close()
            self.logger.info("TimeSeriesDatabase closed successfully.")
        except VectorDatabaseError as e:
            self.logger.error(f"Failed to close TimeSeriesDatabase: {e}", exc_info=True)
            raise GooglePaLMModelsError(f"Failed to close TimeSeriesDatabase: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while closing TimeSeriesDatabase: {e}", exc_info=True)
            raise GooglePaLMModelsError(f"Unexpected error while closing TimeSeriesDatabase: {e}")

        try:
            # Close VectorDatabase
            self.vector_db.close()
            self.logger.info("VectorDatabase closed successfully.")
        except VectorDatabaseError as e:
            self.logger.error(f"Failed to close VectorDatabase: {e}", exc_info=True)
            raise GooglePaLMModelsError(f"Failed to close VectorDatabase: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while closing VectorDatabase: {e}", exc_info=True)
            raise GooglePaLMModelsError(f"Unexpected error while closing VectorDatabase: {e}")

        self.logger.info("GooglePaLMModels closed all resources successfully.")

    def get_model_details(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves detailed information about a specific Google PaLM model.
    
        Args:
            model_id (str): The ID of the model to retrieve details for.
    
        Returns:
            Optional[Dict[str, Any]]: A dictionary containing model details if found, else None.
        """
        try:
            if model_id not in self.available_models:
                self.logger.warning(f"Model '{model_id}' not found in available Google PaLM models.")
                return None

            # Since the list_models method returns model IDs, additional details may require separate calls.
            # Assuming the API provides a way to get model details, else return minimal info.
            url = f"{self.api_endpoint}/{model_id}?key={self.api_key}"
            response = requests.get(url, headers=self.headers, params={'key': self.api_key}, timeout=10)
            response.raise_for_status()
            model_info = response.json()
            self.logger.debug(f"Retrieved details for model '{model_id}': {model_info}")
            return model_info
        except RequestException as e:
            self.logger.error(f"HTTP error while retrieving model details for '{model_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving model details for '{model_id}': {e}", exc_info=True)
            return None
