# services/llm_integration_service.py

import logging
import threading
import requests
from typing import Any, Dict, List, Optional
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

class LLMIntegrationError(Exception):
    """Custom exception for LLM integration failures."""
    pass

class LLMIntegrationService:
    """
    Manages integration with Large Language Models (LLMs) such as OpenAI's GPT.
    Handles sending prompts, receiving responses, managing tokens, and ensuring secure interactions.
    """

    def __init__(self):
        """
        Initializes the LLMIntegrationService with necessary configurations and authentication.
        """
        self.logger = setup_logging('LLMIntegrationService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.api_key = self._load_api_key()
        self.endpoint = self.config_loader.get('LLM_API_ENDPOINT', 'https://api.openai.com/v1/engines/davinci/completions')
        self.headers = self._build_headers()
        self.session = requests.Session()
        self.lock = threading.Lock()
        self.logger.info("LLMIntegrationService initialized successfully.")

    def _load_api_key(self) -> str:
        """
        Loads and decrypts the LLM API key from the configuration.
        
        Returns:
            str: The decrypted API key.
        
        Raises:
            LLMIntegrationError: If the API key is missing or decryption fails.
        """
        try:
            self.logger.debug("Loading LLM API key from configuration.")
            encrypted_key = self.config_loader.get('LLM_API_KEY_ENCRYPTED')
            if not encrypted_key:
                self.logger.error("LLM_API_KEY_ENCRYPTED not found in configuration.")
                raise LLMIntegrationError("LLM_API_KEY_ENCRYPTED not found in configuration.")
            decrypted_key = self.encryption_manager.decrypt_data(encrypted_key)
            api_key = decrypted_key.decode('utf-8')
            self.logger.debug("LLM API key decrypted successfully.")
            return api_key
        except Exception as e:
            self.logger.error(f"Error loading LLM API key: {e}", exc_info=True)
            raise LLMIntegrationError(f"Error loading LLM API key: {e}")

    def _build_headers(self) -> Dict[str, str]:
        """
        Builds the HTTP headers required for LLM API requests.
        
        Returns:
            Dict[str, str]: A dictionary of HTTP headers.
        """
        try:
            self.logger.debug("Building HTTP headers for LLM API requests.")
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            self.logger.debug(f"HTTP headers built: {headers}")
            return headers
        except Exception as e:
            self.logger.error(f"Error building HTTP headers: {e}", exc_info=True)
            raise LLMIntegrationError(f"Error building HTTP headers: {e}")

    def send_prompt(self, prompt: str, max_tokens: int = 150, temperature: float = 0.7, top_p: float = 1.0, n: int = 1, stop: Optional[str] = None) -> Optional[str]:
        """
        Sends a prompt to the LLM and retrieves the generated response.
        
        Args:
            prompt (str): The prompt to send to the LLM.
            max_tokens (int, optional): The maximum number of tokens to generate. Defaults to 150.
            temperature (float, optional): Sampling temperature. Defaults to 0.7.
            top_p (float, optional): Nucleus sampling probability. Defaults to 1.0.
            n (int, optional): Number of completions to generate. Defaults to 1.
            stop (str, optional): Sequence where the API will stop generating further tokens. Defaults to None.
        
        Returns:
            Optional[str]: The generated response from the LLM, or None if failed.
        """
        try:
            self.logger.debug(f"Sending prompt to LLM: {prompt}")
            payload = {
                'prompt': prompt,
                'max_tokens': max_tokens,
                'temperature': temperature,
                'top_p': top_p,
                'n': n,
                'stop': stop
            }
            with self.lock:
                response = self.session.post(self.endpoint, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            generated_text = data['choices'][0]['text'].strip()
            self.logger.info("Prompt sent and response received successfully.")
            return generated_text
        except requests.exceptions.RequestException as e:
            self.logger.error(f"HTTP request error when sending prompt: {e}", exc_info=True)
            return None
        except (KeyError, IndexError) as e:
            self.logger.error(f"Error parsing LLM response: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error when sending prompt: {e}", exc_info=True)
            return None

    def batch_send_prompts(self, prompts: List[str], max_tokens: int = 150, temperature: float = 0.7, top_p: float = 1.0, n: int = 1, stop: Optional[str] = None) -> List[Optional[str]]:
        """
        Sends multiple prompts to the LLM and retrieves the generated responses.
        
        Args:
            prompts (List[str]): A list of prompts to send to the LLM.
            max_tokens (int, optional): The maximum number of tokens to generate per prompt. Defaults to 150.
            temperature (float, optional): Sampling temperature. Defaults to 0.7.
            top_p (float, optional): Nucleus sampling probability. Defaults to 1.0.
            n (int, optional): Number of completions to generate per prompt. Defaults to 1.
            stop (str, optional): Sequence where the API will stop generating further tokens. Defaults to None.
        
        Returns:
            List[Optional[str]]: A list of generated responses from the LLM.
        """
        responses = []
        for prompt in prompts:
            response = self.send_prompt(prompt, max_tokens, temperature, top_p, n, stop)
            responses.append(response)
        return responses

    def stream_response(self, prompt: str, max_tokens: int = 150, temperature: float = 0.7, top_p: float = 1.0, stop: Optional[str] = None):
        """
        Streams the LLM response in real-time as it is being generated.
        
        Args:
            prompt (str): The prompt to send to the LLM.
            max_tokens (int, optional): The maximum number of tokens to generate. Defaults to 150.
            temperature (float, optional): Sampling temperature. Defaults to 0.7.
            top_p (float, optional): Nucleus sampling probability. Defaults to 1.0.
            stop (str, optional): Sequence where the API will stop generating further tokens. Defaults to None.
        
        Yields:
            str: Chunks of the generated response.
        """
        try:
            self.logger.debug(f"Streaming response for prompt: {prompt}")
            payload = {
                'prompt': prompt,
                'max_tokens': max_tokens,
                'temperature': temperature,
                'top_p': top_p,
                'n': 1,
                'stream': True,
                'stop': stop
            }
            with self.lock:
                with self.session.post(self.endpoint, headers=self.headers, json=payload, stream=True, timeout=60) as response:
                    response.raise_for_status()
                    for chunk in response.iter_lines(decode_unicode=True):
                        if chunk:
                            data = chunk.lstrip('data: ')
                            if data == '[DONE]':
                                self.logger.info("Streaming completed.")
                                break
                            try:
                                json_data = requests.utils.json.loads(data)
                                text = json_data['choices'][0]['delta'].get('content', '')
                                if text:
                                    yield text
                            except (ValueError, KeyError) as e:
                                self.logger.error(f"Error parsing streaming data: {e}", exc_info=True)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"HTTP request error during streaming: {e}", exc_info=True)
            yield ""
        except Exception as e:
            self.logger.error(f"Unexpected error during streaming: {e}", exc_info=True)
            yield ""

    def close_session(self):
        """
        Closes the HTTP session.
        """
        try:
            self.logger.debug("Closing HTTP session.")
            self.session.close()
            self.logger.info("HTTP session closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing HTTP session: {e}", exc_info=True)
            raise LLMIntegrationError(f"Error closing HTTP session: {e}")
