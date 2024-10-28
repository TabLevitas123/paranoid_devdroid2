# paranoid_devdroid2.data.databases module initialization
from databases.tracking_system import PineconeTrackingSystem, PineconeTrackingSystemError
from sqlalchemy.engine.url import URL
from modules.security.authentication import AuthenticationManager
import threading
from sqlalchemy.orm import sessionmaker, declarative_base
from modules.utilities.config_loader import ConfigLoader
from prometheus_client.core import CollectorRegistry
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base, relationship
from email.mime.multipart import MIMEMultipart
from prometheus_client import start_http_server, Gauge
from databases.graph_db import GraphDatabaseManager
from modules.security.encryption_manager import EncryptionManager
from influxdb_client.client.exceptions import InfluxDBError
from shared_memory.shared_data_structures import SharedMemoryManager
from email.mime.text import MIMEText
from databases.time_series_db import TimeSeriesDatabase
import logging
from typing import Any, Dict, List, Optional, Tuple
from influxdb_client.client.write_api import SYNCHRONOUS
from sentence_transformers import SentenceTransformer
from neo4j.exceptions import ServiceUnavailable
from databases.sqlite_db import SQLiteDatabase
import smtplib
from pinecone import VectorAlreadyExistsException, VectorNotFoundException, PineconeException
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from datetime import datetime
from contextlib import contextmanager
import pinecone
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Index
from influxdb_client import InfluxDBClient, Point, WritePrecision
import json
from modules.utilities.logging_manager import setup_logging
import os
from typing import Any, Dict, List, Optional
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import Column, String, Integer, Text, create_engine, exists
from pinecone import PineconeException
from databases.vector_db import VectorDatabase
from neo4j import GraphDatabase, Neo4jError
from influxdb_client.client.query_api import QueryApi
