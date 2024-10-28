# paranoid_devdroid2.tests module initialization
from modules.machine_learning.ml_module import MachineLearningModule
from data.models.language_models.openai_models import OpenAIModels, OpenAIModelsError
from data.databases.time_series_db import TimeSeriesDatabase
import threading
from data.models.language_models.azure_models import AzureModels, AzureModelsError
from modules.utilities.config_loader import ConfigLoader
from data.databases.vector_db import VectorDatabase, VectorDatabaseError
from modules.communication.message_broker import MessageBroker, MessageBrokerError
from unittest.mock import MagicMock, patch
from modules.communication.message_broker import MessageBroker
from modules.memory.shared_memory import SharedMemory
from modules.security.encryption_manager import EncryptionManager
from data.models.language_models.anthropic_models import AnthropicModels, AnthropicModelsError
from modules.agent.agent_manager import AgentManager, AgentError
from flask import url_for
from marvin.sub_agents.verifier import Verifier
from modules.services.llm_integration_service import LLMIntegrationService
from data.models.language_models.huggingface_models import HuggingFaceModels, HuggingFaceModelsError
from unittest.mock import patch, MagicMock
from __init__ import app, db, User
from marvin.marvin_agent import MarvinAgent, MarvinAgentError, SubAgent
from flask_testing import TestCase
from marvin.sub_agents.expert_panel import ExpertPanel
from data.models.language_models.cohere_models import CohereModels, CohereModelsError
from marvin.sub_agents.hallucination_monitor import HallucinationMonitor
from __init__ import app, db, User, LogEntry
from modules.communication.communication_module import CommunicationModule
from modules.communication.communication_module import CommunicationModule, CommunicationModuleError
import time
from __init__ import app, db, User, Notification
import json
from modules.utilities.logging_manager import setup_logging
import pytest
from data.shared_memory.shared_data_structures import SharedMemoryManager
import os
from marvin.sub_agents.decider import Decider
from data.models.language_models.google_palm_models import GooglePaLMModels, GooglePaLMModelsError
