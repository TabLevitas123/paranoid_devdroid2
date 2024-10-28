# tests/test_init.py

"""
Unit Tests for Flask Application Initialization

This module contains comprehensive unit tests for the Flask application defined in __init__.py,
ensuring robust functionality, error handling, and security compliance.
"""

import pytest
from flask import url_for
from unittest.mock import patch, MagicMock
from flask_testing import TestCase
from __init__ import app, db, User, CommunicationModule, EncryptionManager

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

def logout(client):
    return client.get('/logout', follow_redirects=True)

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_app_initialization(mock_encryption_manager, mock_communication_module, client):
    """
    Test that the Flask application initializes correctly with all dependencies.
    """
    mock_encryption_manager_instance = mock_encryption_manager.return_value
    mock_communication_module_instance = mock_communication_module.return_value

    # Access the index page
    response = client.get('/')
    assert response.status_code == 200
    assert b"Welcome to the Marvin Agent System" in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_user_login_logout(mock_encryption_manager, mock_communication_module, client):
    """
    Test user login and logout functionalities.
    """
    # Attempt login with correct credentials
    response = login(client, 'testuser', 'testpassword')
    assert response.status_code == 200
    assert b"Dashboard" in response.data

    # Access dashboard
    response = client.get('/dashboard')
    assert response.status_code == 200
    assert b"System Metrics" in response.data

    # Logout
    response = logout(client)
    assert response.status_code == 200
    assert b"Welcome to the Marvin Agent System" in response.data

    # Attempt to access dashboard after logout
    response = client.get('/dashboard', follow_redirects=True)
    assert response.status_code == 200
    assert b"Login" in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_send_message_api_success(mock_encryption_manager, mock_communication_module, client):
    """
    Test successful sending of a message via the API.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Prepare message data
    message_data = {
        "receiver_id": "agent_2",
        "message_type": "task",
        "content": {"action": "generate_text", "data": "Hello, World!"}
    }

    # Send message via API
    response = client.post('/api/send_message', json=message_data)
    assert response.status_code == 200
    assert response.get_json()["status"] == "Message sent successfully."

    # Ensure that send_message was called with correct parameters
    mock_communication_module_instance = mock_communication_module.return_value
    mock_communication_module_instance.send_message.assert_called_once_with(
        sender_id='1',  # Assuming testuser has ID=1
        receiver_id='agent_2',
        message_type='task',
        content={"action": "generate_text", "data": "Hello, World!"}
    )

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_send_message_api_failure(mock_encryption_manager, mock_communication_module, client):
    """
    Test handling of failure when sending a message via the API.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Configure the send_message method to raise an exception
    mock_communication_module_instance = mock_communication_module.return_value
    mock_communication_module_instance.send_message.side_effect = Exception("Send failed")

    # Prepare message data
    message_data = {
        "receiver_id": "agent_2",
        "message_type": "task",
        "content": {"action": "generate_text", "data": "Hello, World!"}
    }

    # Send message via API
    response = client.post('/api/send_message', json=message_data)
    assert response.status_code == 500
    assert response.get_json()["error"] == "Failed to send message."

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_receive_message_api_success(mock_encryption_manager, mock_communication_module, client):
    """
    Test successful receiving of a message via the API.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Prepare mock message
    mock_message = {
        'message_id': 'msg_123',
        'timestamp': 1638316800.0,
        'sender_id': 'agent_1',
        'receiver_id': '1',  # testuser's ID
        'message_type': 'task',
        'content': "encrypted_{'action': 'generate_text', 'data': 'Hello, World!'}"
    }

    # Configure the consume_message method to return the mock message
    mock_communication_module_instance = mock_communication_module.return_value
    mock_communication_module_instance.receive_message.return_value = mock_message

    # Receive message via API
    response = client.get('/api/receive_message?message_type=task&timeout=5')
    assert response.status_code == 200
    received = response.get_json()["message"]
    assert received["message_id"] == "msg_123"
    assert received["sender_id"] == "agent_1"
    assert received["receiver_id"] == "1"
    assert received["message_type"] == "task"
    assert received["content"] == "{'action': 'generate_text', 'data': 'Hello, World!'}"

    # Ensure that receive_message was called with correct parameters
    mock_communication_module_instance.receive_message.assert_called_once_with(
        receiver_id='1',
        message_type_filter='task',
        timeout=5.0
    )

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_receive_message_api_no_message(mock_encryption_manager, mock_communication_module, client):
    """
    Test receiving a message when no message is available.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Configure the consume_message method to return None
    mock_communication_module_instance = mock_communication_module.return_value
    mock_communication_module_instance.receive_message.return_value = None

    # Receive message via API
    response = client.get('/api/receive_message?message_type=task&timeout=1')
    assert response.status_code == 200
    assert response.get_json()["message"] is None

    # Ensure that receive_message was called with correct parameters
    mock_communication_module_instance.receive_message.assert_called_once_with(
        receiver_id='1',
        message_type_filter='task',
        timeout=1.0
    )
