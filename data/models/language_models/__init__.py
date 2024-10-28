# paranoid_devdroid2.data.models.language_models module initialization
import openai
import cohere
from modules.security.encryption_manager import EncryptionManager
from modules.utilities.logging_manager import setup_logging
from modules.security.authentication import AuthenticationManager
from shared_memory.shared_data_structures import SharedMemoryManager
import os
from databases.vector_db import VectorDatabase, VectorDatabaseError
from openai import OpenAIError, AuthenticationError, RateLimitError, APIConnectionError, APIError
from databases.time_series_db import TimeSeriesDatabase
from cohere.errors import CohereError, AuthenticationError, RateLimitError, ServerError
from typing import Any, Dict, Optional, List
from typing import Any, Dict, List, Optional
import logging
import requests
from requests.exceptions import RequestException
from modules.utilities.config_loader import ConfigLoader
