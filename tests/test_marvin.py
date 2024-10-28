# tests/test_marvin.py

"""
Unit Tests for Marvin Module

This module contains comprehensive unit tests for the Marvin service,
ensuring robust functionality, error handling, and security compliance.
"""

import pytest
from unittest.mock import MagicMock, patch
from data.models.language_models.openai_models import OpenAIModels, OpenAIModelsError
from data.models.language_models.google_palm_models import GooglePaLMModels, GooglePaLMModelsError
from data.models.language_models.azure_models import AzureModels, AzureModelsError
from data.models.language_models.huggingface_models import HuggingFaceModels, HuggingFaceModelsError
from data.models.language_models.anthropic_models import AnthropicModels, AnthropicModelsError
from data.models.language_models.cohere_models import CohereModels, CohereModelsError
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager

class TestMarvinService:
    """
    Test Suite for the Marvin Service
    """

    @pytest.fixture(scope="class")
    def marvin_service(self, config_loader, encryption_manager):
        """
        Fixture to initialize the Marvin service with mocked dependencies.
        """
        with patch('modules.language_models.openai_models.requests.get') as mock_openai_get, \
             patch('modules.language_models.google_palm_models.requests.get') as mock_google_palm_get, \
             patch('modules.language_models.azure_models.openai.Completion.list') as mock_azure_completion_list, \
             patch('modules.language_models.huggingface_models.requests.get') as mock_huggingface_get, \
             patch('modules.language_models.anthropic_models.requests.get') as mock_anthropic_get, \
             patch('modules.language_models.cohere_models.cohere.Client.list_models') as mock_cohere_list_models:
            
            # Mock responses for model listings
            mock_openai_get.return_value = MagicMock(status_code=200, json=lambda: {"models": [{"id": "gpt-3.5-turbo"}, {"id": "gpt-4"}]})
            mock_google_palm_get.return_value = MagicMock(status_code=200, json=lambda: {"models": [{"name": "models/text-bison-001"}, {"name": "models/code-bison-001"}]})
            mock_azure_completion_list.return_value = MagicMock(data=[{"id": "text-davinci-003"}, {"id": "gpt-35-turbo"}])
            mock_huggingface_get.return_value = MagicMock(status_code=200, json=lambda: [{"modelId": "gpt2"}, {"modelId": "gpt-j-6B"}])
            mock_anthropic_get.return_value = MagicMock(status_code=200, json=lambda: {"models": [{"name": "claude-v1"}, {"name": "claude-instant-v1"}]})
            mock_cohere_list_models.return_value = MagicMock(models=[MagicMock(id="command-xlarge-nightly"), MagicMock(id="summarize-xlarge")])
            
            # Initialize language models
            openai_models = OpenAIModels()
            google_palm_models = GooglePaLMModels()
            azure_models = AzureModels()
            huggingface_models = HuggingFaceModels()
            anthropic_models = AnthropicModels()
            cohere_models = CohereModels()
            
            # Initialize Marvin service (assuming it aggregates all models)
            marvin = MagicMock()
            marvin.openai_models = openai_models
            marvin.google_palm_models = google_palm_models
            marvin.azure_models = azure_models
            marvin.huggingface_models = huggingface_models
            marvin.anthropic_models = anthropic_models
            marvin.cohere_models = cohere_models
            
            yield marvin
            
            # Teardown if necessary
            openai_models.dispose()
            google_palm_models.dispose()
            azure_models.dispose()
            huggingface_models.dispose()
            anthropic_models.dispose()
            cohere_models.dispose()

    def test_initialization(self, marvin_service):
        """
        Test that the Marvin service initializes all language models correctly.
        """
        assert marvin_service.openai_models is not None
        assert marvin_service.google_palm_models is not None
        assert marvin_service.azure_models is not None
        assert marvin_service.huggingface_models is not None
        assert marvin_service.anthropic_models is not None
        assert marvin_service.cohere_models is not None

    def test_openai_models_list(self, marvin_service):
        """
        Test that OpenAI models are listed correctly.
        """
        models = marvin_service.openai_models.available_models
        assert "gpt-3.5-turbo" in models
        assert "gpt-4" in models

    def test_google_palm_models_list(self, marvin_service):
        """
        Test that Google PaLM models are listed correctly.
        """
        models = marvin_service.google_palm_models.available_models
        assert "models/text-bison-001" in models
        assert "models/code-bison-001" in models

    def test_azure_models_list(self, marvin_service):
        """
        Test that Azure OpenAI models are listed correctly.
        """
        models = marvin_service.azure_models.available_models
        assert "text-davinci-003" in models
        assert "gpt-35-turbo" in models

    def test_huggingface_models_list(self, marvin_service):
        """
        Test that Hugging Face models are listed correctly.
        """
        models = marvin_service.huggingface_models.available_models
        assert "gpt2" in models
        assert "gpt-j-6B" in models

    def test_anthropic_models_list(self, marvin_service):
        """
        Test that Anthropic models are listed correctly.
        """
        models = marvin_service.anthropic_models.available_models
        assert "claude-v1" in models
        assert "claude-instant-v1" in models

    def test_cohere_models_list(self, marvin_service):
        """
        Test that Cohere models are listed correctly.
        """
        models = marvin_service.cohere_models.available_models
        assert "command-xlarge-nightly" in models
        assert "summarize-xlarge" in models

    @pytest.mark.parametrize("provider,model,prompt,expected_text", [
        ("openai", "gpt-3.5-turbo", "Hello, how are you?", "I'm fine, thank you!"),
        ("google_palm", "models/text-bison-001", "Summarize the following text.", "This is a summary."),
        ("azure_openai", "text-davinci-003", "Generate a creative story.", "Once upon a time..."),
        ("huggingface", "gpt2", "Translate to French: Hello", "Bonjour"),
        ("anthropic", "claude-v1", "Explain quantum computing.", "Quantum computing is..."),
        ("cohere", "command-xlarge-nightly", "Provide a brief overview of machine learning.", "Machine learning is...")
    ])
    def test_generate_text_success(self, marvin_service, provider, model, prompt, expected_text):
        """
        Test successful text generation across all language model providers.
        """
        # Mock the generate_text method for each provider
        if provider == "openai":
            marvin_service.openai_models.generate_text = MagicMock(return_value=[{"text": expected_text}])
            response = marvin_service.openai_models.generate_text(prompt=prompt, model=model)
        elif provider == "google_palm":
            marvin_service.google_palm_models.generate_text = MagicMock(return_value=[{"text": expected_text}])
            response = marvin_service.google_palm_models.generate_text(prompt=prompt, model=model)
        elif provider == "azure_openai":
            marvin_service.azure_models.generate_text = MagicMock(return_value=[{"text": expected_text}])
            response = marvin_service.azure_models.generate_text(prompt=prompt, model=model)
        elif provider == "huggingface":
            marvin_service.huggingface_models.generate_text = MagicMock(return_value=[{"text": expected_text}])
            response = marvin_service.huggingface_models.generate_text(prompt=prompt, model=model)
        elif provider == "anthropic":
            marvin_service.anthropic_models.generate_text = MagicMock(return_value=[{"text": expected_text}])
            response = marvin_service.anthropic_models.generate_text(prompt=prompt, model=model)
        elif provider == "cohere":
            marvin_service.cohere_models.generate_text = MagicMock(return_value=[{"text": expected_text}])
            response = marvin_service.cohere_models.generate_text(prompt=prompt, model=model)
        else:
            pytest.fail(f"Unknown provider: {provider}")

        assert response is not None
        assert len(response) == 1
        assert response[0]["text"] == expected_text

    @pytest.mark.parametrize("provider,model,prompt,exception", [
        ("openai", "gpt-3.5-turbo", "Test prompt", OpenAIModelsError),
        ("google_palm", "models/text-bison-001", "Test prompt", GooglePaLMModelsError),
        ("azure_openai", "text-davinci-003", "Test prompt", AzureModelsError),
        ("huggingface", "gpt2", "Test prompt", HuggingFaceModelsError),
        ("anthropic", "claude-v1", "Test prompt", AnthropicModelsError),
        ("cohere", "command-xlarge-nightly", "Test prompt", CohereModelsError)
    ])
    def test_generate_text_api_failure(self, marvin_service, provider, model, prompt, exception):
        """
        Test handling of API failures across all language model providers.
        """
        # Mock the generate_text method to raise an exception
        if provider == "openai":
            marvin_service.openai_models.generate_text = MagicMock(side_effect=exception("API failure"))
            response = marvin_service.openai_models.generate_text(prompt=prompt, model=model)
        elif provider == "google_palm":
            marvin_service.google_palm_models.generate_text = MagicMock(side_effect=exception("API failure"))
            response = marvin_service.google_palm_models.generate_text(prompt=prompt, model=model)
        elif provider == "azure_openai":
            marvin_service.azure_models.generate_text = MagicMock(side_effect=exception("API failure"))
            response = marvin_service.azure_models.generate_text(prompt=prompt, model=model)
        elif provider == "huggingface":
            marvin_service.huggingface_models.generate_text = MagicMock(side_effect=exception("API failure"))
            response = marvin_service.huggingface_models.generate_text(prompt=prompt, model=model)
        elif provider == "anthropic":
            marvin_service.anthropic_models.generate_text = MagicMock(side_effect=exception("API failure"))
            response = marvin_service.anthropic_models.generate_text(prompt=prompt, model=model)
        elif provider == "cohere":
            marvin_service.cohere_models.generate_text = MagicMock(side_effect=exception("API failure"))
            response = marvin_service.cohere_models.generate_text(prompt=prompt, model=model)
        else:
            pytest.fail(f"Unknown provider: {provider}")

        assert response is None

    def test_caching_mechanism(self, marvin_service):
        """
        Test that the caching mechanism works correctly by retrieving cached results
        instead of making new API calls.
        """
        prompt = "Hello, how are you?"
        model = "gpt-3.5-turbo"
        expected_text = "I'm fine, thank you!"
        cache_key = f"huggingface_{model}_{hash(prompt)}_150_0.7_1_1"

        # First call: should generate text and cache it
        marvin_service.openai_models.generate_text = MagicMock(return_value=[{"text": expected_text}])
        response_first = marvin_service.openai_models.generate_text(prompt=prompt, model=model)
        assert response_first is not None
        assert response_first[0]["text"] == expected_text
        marvin_service.shared_memory.cache_data.assert_called_with(key=cache_key, value=[{"text": expected_text}])

        # Reset mock to ensure it is not called again
        marvin_service.openai_models.generate_text.reset_mock()

        # Second call: should retrieve from cache and not call generate_text again
        marvin_service.shared_memory.get_data = MagicMock(return_value=[{"text": expected_text}])
        response_second = marvin_service.openai_models.generate_text(prompt=prompt, model=model)
        assert response_second is not None
        assert response_second[0]["text"] == expected_text
        marvin_service.openai_models.generate_text.assert_not_called()

    def test_dispose_method(self, marvin_service):
        """
        Test that the dispose method correctly closes all integrated services.
        """
        marvin_service.openai_models.dispose = MagicMock()
        marvin_service.google_palm_models.dispose = MagicMock()
        marvin_service.azure_models.dispose = MagicMock()
        marvin_service.huggingface_models.dispose = MagicMock()
        marvin_service.anthropic_models.dispose = MagicMock()
        marvin_service.cohere_models.dispose = MagicMock()

        # Call dispose
        marvin_service.dispose()

        # Assert that dispose was called for all models
        marvin_service.openai_models.dispose.assert_called_once()
        marvin_service.google_palm_models.dispose.assert_called_once()
        marvin_service.azure_models.dispose.assert_called_once()
        marvin_service.huggingface_models.dispose.assert_called_once()
        marvin_service.anthropic_models.dispose.assert_called_once()
        marvin_service.cohere_models.dispose.assert_called_once()
