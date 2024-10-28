# tests/test_logs.py

"""
Unit Tests for Logs Page

This module contains comprehensive unit tests for the logs.html template,
ensuring that system logs are displayed correctly and filtering functions as intended.
"""

import pytest
from flask import url_for
from unittest.mock import patch, MagicMock
from flask_testing import TestCase
from __init__ import app, db, User, LogEntry

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
            # Add sample log entries
            log1 = LogEntry(agent_id='agent_1', level='INFO', message='System started.', timestamp='2021-12-01 10:00:00')
            log2 = LogEntry(agent_id='agent_2', level='ERROR', message='Failed to process task.', timestamp='2021-12-01 11:00:00')
            log3 = LogEntry(agent_id='agent_1', level='WARNING', message='Low disk space.', timestamp='2021-12-01 12:00:00')
            db.session.add_all([log1, log2, log3])
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
def test_logs_page_access_authenticated(mock_encryption_manager, mock_communication_module, client):
    """
    Test that authenticated users can access the logs page.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    response = client.get('/logs')
    assert response.status_code == 200
    assert b"System Logs" in response.data
    assert b"System started." in response.data
    assert b"Failed to process task." in response.data
    assert b"Low disk space." in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_logs_page_access_unauthenticated(mock_encryption_manager, mock_communication_module, client):
    """
    Test that unauthenticated users cannot access the logs page.
    """
    response = client.get('/logs', follow_redirects=True)
    assert response.status_code == 200
    assert b"Login" in response.data
    assert b"Username" in response.data
    assert b"Password" in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_logs_filtering_by_level(mock_encryption_manager, mock_communication_module, client):
    """
    Test filtering logs by log level.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Filter logs with level 'ERROR'
    response = client.get('/logs?level=ERROR')
    assert response.status_code == 200
    assert b"Failed to process task." in response.data
    assert b"System started." not in response.data
    assert b"Low disk space." not in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_logs_filtering_by_agent(mock_encryption_manager, mock_communication_module, client):
    """
    Test filtering logs by agent ID.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Filter logs for agent_1
    response = client.get('/logs?agent=agent_1')
    assert response.status_code == 200
    assert b"System started." in response.data
    assert b"Low disk space." in response.data
    assert b"Failed to process task." not in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_logs_filtering_by_date_range(mock_encryption_manager, mock_communication_module, client):
    """
    Test filtering logs by a specific date range.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Filter logs between 2021-12-01 10:30:00 and 2021-12-01 12:30:00
    response = client.get('/logs?start_date=2021-12-01&end_date=2021-12-01')
    assert response.status_code == 200
    assert b"Failed to process task." in response.data
    assert b"Low disk space." in response.data
    assert b"System started." not in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_logs_no_logs_found(mock_encryption_manager, mock_communication_module, client):
    """
    Test that appropriate message is displayed when no logs match the filter criteria.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Apply a filter that matches no logs
    response = client.get('/logs?level=CRITICAL')
    assert response.status_code == 200
    assert b"No logs found for the selected criteria." in response.data
    assert b"System started." not in response.data
    assert b"Failed to process task." not in response.data
    assert b"Low disk space." not in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_logs_pagination(mock_encryption_manager, mock_communication_module, client):
    """
    Test pagination functionality on the logs page.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Assume there are 3 log entries and pagination is set to 2 per page
    response = client.get('/logs?page=1')
    assert response.status_code == 200
    assert b"System started." in response.data
    assert b"Failed to process task." in response.data
    assert b"Low disk space." not in response.data

    response = client.get('/logs?page=2')
    assert response.status_code == 200
    assert b"Low disk space." in response.data
    assert b"System started." not in response.data
    assert b"Failed to process task." not in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_logs_invalid_page_number(mock_encryption_manager, mock_communication_module, client):
    """
    Test that invalid page numbers are handled gracefully.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Request a non-existent page
    response = client.get('/logs?page=999')
    assert response.status_code == 200
    assert b"No logs found for the selected criteria." in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_logs_invalid_filters(mock_encryption_manager, mock_communication_module, client):
    """
    Test that invalid filter parameters do not break the logs page.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Apply invalid filter parameters
    response = client.get('/logs?level=INVALID_LEVEL&agent=nonexistent_agent&start_date=invalid_date&end_date=invalid_date')
    assert response.status_code == 200
    assert b"No logs found for the selected criteria." in response.data
