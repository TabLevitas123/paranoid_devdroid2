# tests/test_templates.py

"""
Unit Tests for HTML Templates Rendering

This module contains unit tests to ensure that HTML templates render correctly
with the expected context data and adhere to security best practices.
"""

import pytest
from flask import url_for
from unittest.mock import patch, MagicMock
from flask_testing import TestCase
from __init__ import app, db, User

class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SECRET_KEY = 'Test_Secret_Key'
    WTF_CSRF_ENABLED = False  # Disable CSRF for testing purposes

@pytest.fixture
def client():
    app.config.from_object(TestConfig)
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            # Create a test user
            user = User(username='testuser', email='test@example.com')
            user.set_password('testpassword')
            db.session.add(user)
            db.session.commit()
        yield client
        with app.app_context():
            db.session.remove()
            db.drop_all()

def login(client, username, password):
    return client.post('/login', data=dict(
        username=username,
        password=password
    ), follow_redirects=True)

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_index_page(client, mock_encryption_manager, mock_communication_module):
    """
    Test rendering of the index.html template.
    """
    response = client.get('/')
    assert response.status_code == 200
    assert b"Welcome to the Marvin Agent System" in response.data
    assert b"Get Started" in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_dashboard_page_authenticated(client, mock_encryption_manager, mock_communication_module):
    """
    Test rendering of the dashboard.html template for authenticated users.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Prepare mock metrics
    mock_metrics = {
        "cpu_usage": "15%",
        "memory_usage": "45%",
        "disk_space": "70%",
        "active_agents": 5,
        "tasks_processed": 120
    }

    with patch('__init__.get_system_metrics', return_value=mock_metrics):
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert b"Dashboard" in response.data
        assert b"CPU Usage" in response.data
        assert b"15%" in response.data
        assert b"Memory Usage" in response.data
        assert b"45%" in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_dashboard_page_unauthenticated(client, mock_encryption_manager, mock_communication_module):
    """
    Test that unauthenticated users cannot access the dashboard.html template.
    """
    response = client.get('/dashboard', follow_redirects=True)
    assert response.status_code == 200
    assert b"Login" in response.data
    assert b"Username" in response.data
    assert b"Password" in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_metrics_page_authenticated(client, mock_encryption_manager, mock_communication_module):
    """
    Test rendering of the metrics.html template for authenticated users.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Prepare mock metrics with detailed data
    mock_metrics = {
        "cpu_usage": "15%",
        "memory_usage": "45%",
        "disk_space": "70%",
        "active_agents": 5,
        "cpu_usage_over_time": {
            "labels": ["10:00", "11:00", "12:00", "13:00"],
            "data": [10, 20, 15, 15]
        },
        "memory_usage_over_time": {
            "labels": ["10:00", "11:00", "12:00", "13:00"],
            "data": [40, 50, 45, 45]
        },
        "disk_space_used": 70,
        "disk_space_free": 30,
        "agent_activity_over_time": {
            "labels": ["10:00", "11:00", "12:00", "13:00"],
            "data": [20, 25, 30, 25]
        },
        "system_logs": "2021-12-01 10:00:00 INFO Starting system...\n2021-12-01 11:00:00 INFO Processing tasks...\n"
    }

    with patch('__init__.metrics', return_value=mock_metrics):
        response = client.get('/metrics')
        assert response.status_code == 200
        assert b"Detailed Metrics" in response.data
        assert b"CPU Usage" in response.data
        assert b"15%" in response.data
        assert b"Memory Usage" in response.data
        assert b"45%" in response.data
        assert b"System Logs" in response.data
        assert b"Starting system..." in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_metrics_page_unauthenticated(client, mock_encryption_manager, mock_communication_module):
    """
    Test that unauthenticated users cannot access the metrics.html template.
    """
    response = client.get('/metrics', follow_redirects=True)
    assert response.status_code == 200
    assert b"Login" in response.data
    assert b"Username" in response.data
    assert b"Password" in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_error_page(client, mock_encryption_manager, mock_communication_module):
    """
    Test rendering of the error.html template.
    """
    with patch('modules.communication.communication_module.CommunicationModule.send_message', side_effect=Exception("Test Error")):
        login(client, 'testuser', 'testpassword')
        # Trigger an error by sending a message that raises an exception
        message_data = {
            "receiver_id": "agent_2",
            "message_type": "task",
            "content": {"action": "generate_text", "data": "Hello, World!"}
        }
        response = client.post('/api/send_message', json=message_data)
        assert response.status_code == 500
        assert b"An error occurred during login." not in response.data  # Specific error message
        assert b"An error occurred while processing the task." not in response.data
        assert b"An unexpected error occurred." not in response.data  # General error message

def test_csrf_protection(client):
    """
    Test that CSRF protection is active by attempting a POST request without CSRF token.
    """
    app.config['WTF_CSRF_ENABLED'] = True
    response = client.post('/login', data=dict(
        username='testuser',
        password='testpassword'
    ))
    assert response.status_code == 400
    assert b"CSRF token missing" in response.data
    app.config['WTF_CSRF_ENABLED'] = False
