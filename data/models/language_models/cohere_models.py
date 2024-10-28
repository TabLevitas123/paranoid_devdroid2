# language_models/cohere_models.py

import logging
from typing import Any, Dict, Optional, List

import cohere
from cohere.errors import CohereError, AuthenticationError, RateLimitError, ServerError

from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from databases.vector_db import VectorDatabase, VectorDatabaseError
from shared_memory.shared_data_structures import SharedMemoryManager
from databases.time_series_db import TimeSeriesDatabase


class CohereModelsError(Exception):
    """Custom exception for CohereModels-related errors."""
    pass


class CohereModels:
    """
    Manages interactions with Cohere's language models.
    Provides methods to generate text, list available models, and handle model-specific operations.
    Integrates with VectorDatabase, SharedMemoryManager, and TimeSeriesDatabase for enhanced functionalities.
    """

    def __init__(self):
        """
        Initializes the CohereModels with necessary configurations, authentication, and integrations.
        """
        # Setup logging
        self.logger = setup_logging('CohereModels')

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
            raise CohereModelsError(f"Failed to integrate with other systems: {e}")

        # Initialize Cohere API configurations
        try:
            self.cohere_api_key_encrypted = self.config_loader.get('COHERE_API_KEY_ENCRYPTED')
            self.cohere_api_endpoint = self.config_loader.get('COHERE_API_ENDPOINT', 'https://api.cohere.ai')

            if not self.cohere_api_key_encrypted:
                self.logger.error("Cohere API key is missing in configurations.")
                raise CohereModelsError("Cohere API key is missing in configurations.")

            self.cohere_api_key = self.encryption_manager.decrypt_data(self.cohere_api_key_encrypted).decode('utf-8')
            self.client = cohere.Client(self.cohere_api_key, api_version='v1')
            self.logger.info("Cohere API key set successfully.")
        except Exception as e:
            self.logger.error(f"Failed to initialize Cohere API configurations: {e}", exc_info=True)
            raise CohereModelsError(f"Failed to initialize Cohere API configurations: {e}")

        # Initialize model list
        try:
            self.available_models = self.list_models()
            self.logger.info(f"Retrieved {len(self.available_models)} Cohere models.")
        except CohereModelsError as e:
            self.logger.error(f"Failed to retrieve Cohere models: {e}", exc_info=True)
            raise e
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving Cohere models: {e}", exc_info=True)
            raise CohereModelsError(f"Unexpected error while retrieving Cohere models: {e}")

    def list_models(self) -> List[str]:
        """
        Retrieves a list of all available Cohere models.

        Returns:
            List[str]: A list of model IDs.
        """
        try:
            models = self.client.list_models().models
            model_ids = [model.id for model in models]
            self.logger.debug(f"Retrieved models: {model_ids}")
            return model_ids
        except AuthenticationError as e:
            self.logger.error(f"Authentication error while listing Cohere models: {e}", exc_info=True)
            raise CohereModelsError(f"Authentication error while listing Cohere models: {e}")
        except RateLimitError as e:
            self.logger.error(f"Rate limit exceeded while listing Cohere models: {e}", exc_info=True)
            raise CohereModelsError(f"Rate limit exceeded while listing Cohere models: {e}")
        except ServerError as e:
            self.logger.error(f"Server error while listing Cohere models: {e}", exc_info=True)
            raise CohereModelsError(f"Server error while listing Cohere models: {e}")
        except CohereError as e:
            self.logger.error(f"Cohere API error while listing models: {e}", exc_info=True)
            raise CohereModelsError(f"Cohere API error while listing models: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while listing Cohere models: {e}", exc_info=True)
            raise CohereModelsError(f"Unexpected error while listing Cohere models: {e}")

    def generate_text(
        self,
        prompt: str,
        model: str = "command-xlarge-nightly",
        max_tokens: int = 150,
        temperature: float = 0.7,
        top_p: float = 1.0,
        n: int = 1,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Generates text using the specified Cohere model.

        Args:
            prompt (str): The input text prompt for the model.
            model (str, optional): The Cohere model to use. Defaults to "command-xlarge-nightly".
            max_tokens (int, optional): The maximum number of tokens to generate. Defaults to 150.
            temperature (float, optional): Sampling temperature. Defaults to 0.7.
            top_p (float, optional): Top-p sampling probability. Defaults to 1.0.
            n (int, optional): Number of completions to generate. Defaults to 1.
            stop (Optional[List[str]], optional): Stop sequences. Defaults to None.
            **kwargs: Additional parameters for Cohere API.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of generated text completions if successful, else None.
        """
        try:
            # Validate model
            if model not in self.available_models:
                self.logger.error(f"Model '{model}' is not available in Cohere models.")
                return None

            # Check if result is cached
            cache_key = f"cohere_{model}_{hash(prompt)}_{max_tokens}_{temperature}_{top_p}_{n}"
            cached_result = self.shared_memory.get_data(key=cache_key)
            if cached_result:
                self.logger.info(f"Retrieved cached result for key '{cache_key}'.")
                return cached_result

            # Make API request
            self.logger.info(f"Generating text with model '{model}' for prompt: {prompt}")
            response = self.client.generate(
                model=model,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                p=top_p,
                num_generations=n,
                stop_sequences=stop,
                **kwargs
            )

            # Extract completions
            completions = []
            for i, generation in enumerate(response.generations):
                generated_text = generation.text
                completion = {
                    "text": generated_text,
                    "index": i,
                    "logprobs": None,  # Logprobs not available
                    "finish_reason": "eos"  # Assuming end of sequence
                }
                completions.append(completion)
            self.logger.debug(f"Generated completions: {completions}")

            # Cache the result
            self.shared_memory.cache_data(key=cache_key, value=completions)
            self.logger.debug(f"Cached result with key '{cache_key}'.")

            # Log the generation event
            self.time_series_db.log_event(
                event_type='cohere_text_generation',
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
        except AuthenticationError as e:
            self.logger.error(f"Authentication error with Cohere API: {e}", exc_info=True)
            return None
        except RateLimitError as e:
            self.logger.error(f"Rate limit exceeded with Cohere API: {e}", exc_info=True)
            return None
        except ServerError as e:
            self.logger.error(f"Server error with Cohere API: {e}", exc_info=True)
            return None
        except CohereError as e:
            self.logger.error(f"Cohere API error during text generation: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during text generation with Cohere: {e}", exc_info=True)
            return None

    def dispose(self):
        """
        Disposes of all resources and integrations.
        """
        try:
            self.close()
        except CohereModelsError as e:
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
            raise CohereModelsError(f"Failed to close SharedMemoryManager: {e}")

        try:
            # Close TimeSeriesDatabase
            self.time_series_db.close()
            self.logger.info("TimeSeriesDatabase closed successfully.")
        except VectorDatabaseError as e:
            self.logger.error(f"Failed to close TimeSeriesDatabase: {e}", exc_info=True)
            raise CohereModelsError(f"Failed to close TimeSeriesDatabase: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while closing TimeSeriesDatabase: {e}", exc_info=True)
            raise CohereModelsError(f"Unexpected error while closing TimeSeriesDatabase: {e}")

        try:
            # Close VectorDatabase
            self.vector_db.close()
            self.logger.info("VectorDatabase closed successfully.")
        except VectorDatabaseError as e:
            self.logger.error(f"Failed to close VectorDatabase: {e}", exc_info=True)
            raise CohereModelsError(f"Failed to close VectorDatabase: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while closing VectorDatabase: {e}", exc_info=True)
            raise CohereModelsError(f"Unexpected error while closing VectorDatabase: {e}")

        self.logger.info("CohereModels closed all resources successfully.")

    def get_model_details(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves detailed information about a specific Cohere model.

        Args:
            model_id (str): The ID of the model to retrieve details for.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing model details if found, else None.
        """
        try:
            if model_id not in self.available_models:
                self.logger.warning(f"Model '{model_id}' not found in available Cohere models.")
                return None

            model_info = self.client.get_model(model_id)
            self.logger.debug(f"Retrieved details for model '{model_id}': {model_info}")
            return model_info
        except CohereError as e:
            self.logger.error(f"Cohere API error while retrieving model details for '{model_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving model details for '{model_id}': {e}", exc_info=True)
            return None
