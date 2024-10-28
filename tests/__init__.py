# tests/__init__.py

"""
Test Package Initialization

This package contains all unit tests for the application modules,
including Marvin and Agents. It utilizes pytest as the testing framework
and employs fixtures for setup and teardown processes.
"""

import pytest
from unittest.mock import patch
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager

@pytest.fixture(scope="session")
def config_loader():
    """
    Fixture to initialize and provide the ConfigLoader instance for tests.
    """
    return ConfigLoader()

@pytest.fixture(scope="session")
def encryption_manager():
    """
    Fixture to initialize and provide the EncryptionManager instance for tests.
    """
    return EncryptionManager()

@pytest.fixture(scope="function", autouse=True)
def mock_external_dependencies():
    """
    Fixture to mock external dependencies such as API calls to ensure tests are isolated
    and do not make actual network requests.
    """
    with patch('modules.language_models.openai_models.requests.post') as mock_openai_post, \
         patch('modules.language_models.google_palm_models.requests.post') as mock_google_palm_post, \
         patch('modules.language_models.azure_models.openai.Completion.create') as mock_azure_completion_create, \
         patch('modules.language_models.huggingface_models.requests.post') as mock_huggingface_post, \
         patch('modules.language_models.anthropic_models.requests.post') as mock_anthropic_post, \
         patch('modules.language_models.cohere_models.cohere.Client.generate') as mock_cohere_generate:
        yield
