import pickle
from sklearn.model_selection import train_test_split
import pandas as pd
from modules.security.encryption_manager import EncryptionManager
from modules.utilities.logging_manager import setup_logging
from modules.security.authentication import AuthenticationManager
import os
from shared_memory.shared_data_structures import SharedMemoryManager
from databases.vector_db import VectorDatabase, VectorDatabaseError
from typing import Any, Dict, Optional
from databases.time_series_db import TimeSeriesDatabase
from sklearn.linear_model import LogisticRegression
import logging
from sklearn.metrics import classification_report, accuracy_score, f1_score
from sklearn.metrics import classification_report, accuracy_score
from sklearn.ensemble import RandomForestClassifier
import numpy as np
from modules.utilities.config_loader import ConfigLoader