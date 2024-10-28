# paranoid_devdroid2.scripts module initialization
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydantic import BaseModel
from sklearn.model_selection import GridSearchCV, cross_val_score
from fastapi import FastAPI, HTTPException
from sklearn.compose import ColumnTransformer
from typing import Any, Dict
import numpy as np
from typing import Dict, Any
import joblib
import logging
from sklearn.impute import SimpleImputer
from sklearn.ensemble import RandomForestClassifier
import requests
from turtle import pd
from sklearn.model_selection import train_test_split
from typing import Dict, Any, List
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score, accuracy_score
from sklearn.pipeline import Pipeline
import uvicorn
import time
import json
import os
from starlette.middleware.cors import CORSMiddleware
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from typing import Tuple, Dict, Any
