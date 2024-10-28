# language_models/azure_models.py

import logging
import os
from typing import Any, Dict, Optional, List

import openai
from openai import OpenAIError, AuthenticationError, RateLimitError, APIConnectionError, APIError

from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from databases.vector_db import VectorDatabase, VectorDatabaseError
from shared_memory.shared_data_structures import SharedMemoryManager
from databases.time_series_db import TimeSeriesDatabase


class AzureModelsError(Exception):
    """Custom exception for AzureModels-related errors."""
    pass


class AzureModels:
    """
    Manages interactions with Azure's OpenAI language models.
    Provides methods to generate text, list available models, and handle model-specific operations.
    Integrates with VectorDatabase, SharedMemoryManager, and TimeSeriesDatabase for enhanced functionalities.
    """

    def __init__(self):
        """
        Initializes the AzureModels with necessary configurations, authentication, and integrations.
        """
        # Setup logging
        self.logger = setup_logging('AzureModels')

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
            raise AzureModelsError(f"Failed to integrate with other systems: {e}")

        # Initialize Azure OpenAI API configurations
        try:
            self.azure_api_key_encrypted = self.config_loader.get('AZURE_OPENAI_API_KEY_ENCRYPTED')
            self.azure_endpoint_encrypted = self.config_loader.get('AZURE_OPENAI_ENDPOINT_ENCRYPTED')
            self.azure_deployment_name_encrypted = self.config_loader.get('AZURE_OPENAI_DEPLOYMENT_NAME_ENCRYPTED')
    
            if not all([self.azure_api_key_encrypted, self.azure_endpoint_encrypted, self.azure_deployment_name_encrypted]):
                self.logger.error("Azure OpenAI API key, Endpoint, or Deployment Name is missing in configurations.")
                raise AzureModelsError("Azure OpenAI API key, Endpoint, or Deployment Name is missing in configurations.")
    
            self.azure_api_key = self.encryption_manager.decrypt_data(self.azure_api_key_encrypted).decode('utf-8')
            self.azure_endpoint = self.encryption_manager.decrypt_data(self.azure_endpoint_encrypted).decode('utf-8').rstrip('/')
            self.azure_deployment_name = self.encryption_manager.decrypt_data(self.azure_deployment_name_encrypted).decode('utf-8')
            self.logger.info("Azure OpenAI API configurations set successfully.")
    
            # Initialize OpenAI with Azure settings
            openai.api_type = "azure"
            openai.api_base = self.azure_endpoint
            openai.api_version = self.config_loader.get('AZURE_OPENAI_API_VERSION', '2023-05-15')
            openai.api_key = self.azure_api_key
        except Exception as e:
            self.logger.error(f"Failed to initialize Azure OpenAI API configurations: {e}", exc_info=True)
            raise AzureModelsError(f"Failed to initialize Azure OpenAI API configurations: {e}")

        # Initialize model list
        try:
            self.available_models = self.list_models()
            self.logger.info(f"Retrieved {len(self.available_models)} Azure OpenAI models.")
        except OpenAIError as e:
            self.logger.error(f"Failed to retrieve Azure OpenAI models: {e}", exc_info=True)
            raise AzureModelsError(f"Failed to retrieve Azure OpenAI models: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving Azure OpenAI models: {e}", exc_info=True)
            raise AzureModelsError(f"Unexpected error while retrieving Azure OpenAI models: {e}")

    def list_models(self) -> List[str]:
        """
        Retrieves a list of all available Azure OpenAI models.
    
        Returns:
            List[str]: A list of model IDs.
        """
        try:
            response = openai.Model.list()
            models = [model['id'] for model in response['data']]
            self.logger.debug(f"Retrieved models: {models}")
            return models
        except OpenAIError as e:
            self.logger.error(f"OpenAI error while listing Azure models: {e}", exc_info=True)
            raise e
        except Exception as e:
            self.logger.error(f"Unexpected error while listing Azure models: {e}", exc_info=True)
            raise e

    def generate_text(
        self,
        prompt: str,
        model: str = "text-davinci-003",
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
        Generates text using the specified Azure OpenAI model.
    
        Args:
            prompt (str): The input text prompt for the model.
            model (str, optional): The Azure OpenAI model to use. Defaults to "text-davinci-003".
            max_tokens (int, optional): The maximum number of tokens to generate. Defaults to 150.
            temperature (float, optional): Sampling temperature. Defaults to 0.7.
            top_p (float, optional): Top-p sampling probability. Defaults to 1.0.
            n (int, optional): Number of completions to generate. Defaults to 1.
            stop (Optional[List[str]], optional): Stop sequences. Defaults to None.
            stream (bool, optional): Whether to stream the responses. Defaults to False.
            logprobs (Optional[int], optional): Number of logprobs to return. Defaults to None.
            echo (bool, optional): Whether to echo the prompt in the response. Defaults to False.
            **kwargs: Additional parameters for Azure OpenAI API.
    
        Returns:
            Optional[List[Dict[str, Any]]]: A list of generated text completions if successful, else None.
        """
        try:
            # Validate model
            if model not in self.available_models:
                self.logger.error(f"Model '{model}' is not available in Azure OpenAI models.")
                return None

            # Check if result is cached
            cache_key = f"azure_openai_{model}_{hash(prompt)}_{max_tokens}_{temperature}_{top_p}_{n}"
            cached_result = self.shared_memory.get_data(key=cache_key)
            if cached_result:
                self.logger.info(f"Retrieved cached result for key '{cache_key}'.")
                return cached_result

            # Make API request
            self.logger.info(f"Generating text with Azure model '{model}' for prompt: {prompt}")
            response = openai.Completion.create(
                engine=self.azure_deployment_name,
                prompt=prompt,
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
                    "text": choice.text,
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
                event_type='azure_openai_text_generation',
                details={
                    'model': model,
                    'prompt': prompt,
                    'max_tokens': max_tokens,
                    'temperature': temperature,
                    'top_p': top_p,
                    'n': n,
                    'stop_sequences': stop,
                    'stream': stream,
                    'logprobs': logprobs,
                    'echo': echo,
                    'completions_count': len(completions)
                }
            )

            return completions
        except AuthenticationError as e:
            self.logger.error(f"Authentication error with Azure OpenAI API: {e}", exc_info=True)
            return None
        except RateLimitError as e:
            self.logger.error(f"Rate limit exceeded with Azure OpenAI API: {e}", exc_info=True)
            return None
        except APIConnectionError as e:
            self.logger.error(f"API connection error with Azure OpenAI API: {e}", exc_info=True)
            return None
        except APIError as e:
            self.logger.error(f"API error with Azure OpenAI API: {e}", exc_info=True)
            return None
        except OpenAIError as e:
            self.logger.error(f"OpenAI error during text generation with Azure: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during text generation with Azure OpenAI: {e}", exc_info=True)
            return None

    def dispose(self):
        """
        Disposes of all resources and integrations.
        """
        try:
            self.close()
        except AzureModelsError as e:
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
            raise AzureModelsError(f"Failed to close SharedMemoryManager: {e}")

        try:
            # Close TimeSeriesDatabase
            self.time_series_db.close()
            self.logger.info("TimeSeriesDatabase closed successfully.")
        except VectorDatabaseError as e:
            self.logger.error(f"Failed to close TimeSeriesDatabase: {e}", exc_info=True)
            raise AzureModelsError(f"Failed to close TimeSeriesDatabase: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while closing TimeSeriesDatabase: {e}", exc_info=True)
            raise AzureModelsError(f"Unexpected error while closing TimeSeriesDatabase: {e}")

        try:
            # Close VectorDatabase
            self.vector_db.close()
            self.logger.info("VectorDatabase closed successfully.")
        except VectorDatabaseError as e:
            self.logger.error(f"Failed to close VectorDatabase: {e}", exc_info=True)
            raise AzureModelsError(f"Failed to close VectorDatabase: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while closing VectorDatabase: {e}", exc_info=True)
            raise AzureModelsError(f"Unexpected error while closing VectorDatabase: {e}")

        self.logger.info("AzureModels closed all resources successfully.")

    def get_model_details(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves detailed information about a specific Azure OpenAI model.
    
        Args:
            model_id (str): The ID of the model to retrieve details for.
    
        Returns:
            Optional[Dict[str, Any]]: A dictionary containing model details if found, else None.
        """
        try:
            if model_id not in self.available_models:
                self.logger.warning(f"Model '{model_id}' not found in available Azure OpenAI models.")
                return None

            # Assuming that Azure OpenAI does not provide detailed model info via API, return minimal info
            model_info = {
                'id': model_id,
                'description': 'Azure OpenAI model description not available.',
                'created_at': None,
                'updated_at': None
            }
            self.logger.debug(f"Retrieved details for model '{model_id}': {model_info}")
            return model_info
        except Exception as e:
            self.logger.error(f"Failed to retrieve model details for '{model_id}': {e}", exc_info=True)
            return None
