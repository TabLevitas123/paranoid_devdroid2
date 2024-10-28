# language_models/openai_models.py

import logging
import os
from typing import Any, Dict, List, Optional

import openai
from openai import OpenAIError, AuthenticationError, RateLimitError, APIConnectionError, APIError

from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from databases.vector_db import VectorDatabase, VectorDatabaseError
from shared_memory.shared_data_structures import SharedMemoryManager
from databases.time_series_db import TimeSeriesDatabase


class OpenAIModelsError(Exception):
    """Custom exception for OpenAIModels-related errors."""
    pass


class OpenAIModels:
    """
    Manages interactions with OpenAI's language models.
    Provides methods to generate text, list available models, and handle model-specific operations.
    Integrates with VectorDatabase, SharedMemoryManager, and TimeSeriesDatabase for enhanced functionalities.
    """

    def __init__(self):
        """
        Initializes the OpenAIModels with necessary configurations, authentication, and integrations.
        """
        # Setup logging
        self.logger = setup_logging('OpenAIModels')

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
            raise OpenAIModelsError(f"Failed to integrate with other systems: {e}")

        # Initialize OpenAI API key securely
        try:
            openai_api_key_encrypted = self.config_loader.get('OPENAI_API_KEY_ENCRYPTED')
            if not openai_api_key_encrypted:
                self.logger.error("OpenAI API key is missing in configurations.")
                raise OpenAIModelsError("OpenAI API key is missing in configurations.")

            openai_api_key = self.encryption_manager.decrypt_data(openai_api_key_encrypted).decode('utf-8')
            openai.api_key = openai_api_key
            self.logger.info("OpenAI API key set successfully.")
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenAI API key: {e}", exc_info=True)
            raise OpenAIModelsError(f"Failed to initialize OpenAI API key: {e}")

        # Initialize model list
        try:
            self.available_models = self.list_models()
            self.logger.info(f"Retrieved {len(self.available_models)} OpenAI models.")
        except OpenAIError as e:
            self.logger.error(f"Failed to retrieve OpenAI models: {e}", exc_info=True)
            raise OpenAIModelsError(f"Failed to retrieve OpenAI models: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving OpenAI models: {e}", exc_info=True)
            raise OpenAIModelsError(f"Unexpected error while retrieving OpenAI models: {e}")

    def list_models(self) -> List[Dict[str, Any]]:
        """
        Retrieves a list of all available OpenAI models.
    
        Returns:
            List[Dict[str, Any]]: A list of model information dictionaries.
        """
        try:
            response = openai.Model.list()
            models = response['data']
            self.logger.debug(f"Retrieved models: {[model['id'] for model in models]}")
            return models
        except OpenAIError as e:
            self.logger.error(f"OpenAI error while listing models: {e}", exc_info=True)
            raise e
        except Exception as e:
            self.logger.error(f"Unexpected error while listing models: {e}", exc_info=True)
            raise e

    def generate_text(
        self,
        prompt: str,
        model: str = "gpt-3.5-turbo",
        max_tokens: int = 150,
        temperature: float = 0.7,
        top_p: float = 1.0,
        n: int = 1,
        stop: Optional[List[str]] = None,
        stream: bool = False,
        logprobs: Optional[int] = None,
        echo: bool = False,
        **kwargs
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Generates text using the specified OpenAI model.
    
        Args:
            prompt (str): The input text prompt for the model.
            model (str, optional): The OpenAI model to use. Defaults to "gpt-3.5-turbo".
            max_tokens (int, optional): The maximum number of tokens to generate. Defaults to 150.
            temperature (float, optional): Sampling temperature. Defaults to 0.7.
            top_p (float, optional): Top-p sampling probability. Defaults to 1.0.
            n (int, optional): Number of completions to generate. Defaults to 1.
            stop (Optional[List[str]], optional): Stop sequences. Defaults to None.
            stream (bool, optional): Whether to stream the responses. Defaults to False.
            logprobs (Optional[int], optional): Number of logprobs to return. Defaults to None.
            echo (bool, optional): Whether to echo the prompt in the response. Defaults to False.
            **kwargs: Additional parameters for OpenAI API.
    
        Returns:
            Optional[List[Dict[str, Any]]]: A list of generated text completions if successful, else None.
        """
        try:
            # Validate model
            model_ids = [model_info['id'] for model_info in self.available_models]
            if model not in model_ids:
                self.logger.error(f"Model '{model}' is not available in OpenAI models.")
                return None

            # Check if result is cached
            cache_key = f"openai_{model}_{hash(prompt)}_{max_tokens}_{temperature}_{top_p}_{n}"
            cached_result = self.shared_memory.get_data(key=cache_key)
            if cached_result:
                self.logger.info(f"Retrieved cached result for key '{cache_key}'.")
                return cached_result

            # Make API request
            self.logger.info(f"Generating text with model '{model}' for prompt: {prompt}")
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                n=n,
                stop=stop,
                stream=stream,
                logprobs=logprobs,
                echo=echo,
                **kwargs
            )

            # Extract completions
            completions = []
            for choice in response.choices:
                completion = {
                    "text": choice.message['content'] if 'content' in choice.message else choice.text,
                    "index": choice.index,
                    "logprobs": choice.logprobs,
                    "finish_reason": choice.finish_reason
                }
                completions.append(completion)
            self.logger.debug(f"Generated completions: {completions}")

            # Cache the result
            self.shared_memory.cache_data(key=cache_key, value=completions)
            self.logger.debug(f"Cached result with key '{cache_key}'.")

            # Log the generation event
            self.time_series_db.log_event(
                event_type='openai_text_generation',
                details={
                    'model': model,
                    'prompt': prompt,
                    'max_tokens': max_tokens,
                    'temperature': temperature,
                    'top_p': top_p,
                    'n': n,
                    'stop': stop,
                    'stream': stream,
                    'logprobs': logprobs,
                    'echo': echo,
                    'completions_count': len(completions)
                }
            )

            return completions
        except AuthenticationError as e:
            self.logger.error(f"Authentication error with OpenAI API: {e}", exc_info=True)
            return None
        except RateLimitError as e:
            self.logger.error(f"Rate limit exceeded with OpenAI API: {e}", exc_info=True)
            return None
        except APIConnectionError as e:
            self.logger.error(f"API connection error with OpenAI API: {e}", exc_info=True)
            return None
        except APIError as e:
            self.logger.error(f"API error with OpenAI API: {e}", exc_info=True)
            return None
        except OpenAIError as e:
            self.logger.error(f"OpenAI error during text generation: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during text generation: {e}", exc_info=True)
            return None

    def list_available_models(self) -> List[str]:
        """
        Returns a list of available OpenAI model IDs.
    
        Returns:
            List[str]: A list of model IDs.
        """
        try:
            model_ids = [model_info['id'] for model_info in self.available_models]
            self.logger.debug(f"Available OpenAI models: {model_ids}")
            return model_ids
        except Exception as e:
            self.logger.error(f"Failed to list available OpenAI models: {e}", exc_info=True)
            return []

    def get_model_details(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves detailed information about a specific OpenAI model.
    
        Args:
            model_id (str): The ID of the model to retrieve details for.
    
        Returns:
            Optional[Dict[str, Any]]: A dictionary containing model details if found, else None.
        """
        try:
            for model_info in self.available_models:
                if model_info['id'] == model_id:
                    self.logger.debug(f"Retrieved details for model '{model_id}': {model_info}")
                    return model_info
            self.logger.warning(f"Model '{model_id}' not found in available models.")
            return None
        except Exception as e:
            self.logger.error(f"Failed to retrieve model details for '{model_id}': {e}", exc_info=True)
            return None

    def dispose(self):
        """
        Disposes of all resources and integrations.
        """
        try:
            self.close()
        except OpenAIModelsError as e:
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
            raise OpenAIModelsError(f"Failed to close SharedMemoryManager: {e}")

        try:
            # Close TimeSeriesDatabase
            self.time_series_db.close()
            self.logger.info("TimeSeriesDatabase closed successfully.")
        except VectorDatabaseError as e:
            self.logger.error(f"Failed to close TimeSeriesDatabase: {e}", exc_info=True)
            raise OpenAIModelsError(f"Failed to close TimeSeriesDatabase: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while closing TimeSeriesDatabase: {e}", exc_info=True)
            raise OpenAIModelsError(f"Unexpected error while closing TimeSeriesDatabase: {e}")

        try:
            # Close VectorDatabase
            self.vector_db.close()
            self.logger.info("VectorDatabase closed successfully.")
        except VectorDatabaseError as e:
            self.logger.error(f"Failed to close VectorDatabase: {e}", exc_info=True)
            raise OpenAIModelsError(f"Failed to close VectorDatabase: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while closing VectorDatabase: {e}", exc_info=True)
            raise OpenAIModelsError(f"Unexpected error while closing VectorDatabase: {e}")

        self.logger.info("OpenAIModels closed all resources successfully.")
