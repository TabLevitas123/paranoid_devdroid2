# tests/test_settings.py

"""
Unit Tests for Settings Page

This module contains comprehensive unit tests for the settings.html template,
ensuring that profile updates function correctly and adhere to security best practices.
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
def test_settings_page_access_authenticated(mock_encryption_manager, mock_communication_module, client):
    """
    Test that authenticated users can access the settings page.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    response = client.get('/settings')
    assert response.status_code == 200
    assert b"Profile Settings" in response.data
    assert b"Update Settings" in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_settings_page_access_unauthenticated(mock_encryption_manager, mock_communication_module, client):
    """
    Test that unauthenticated users cannot access the settings page.
    """
    response = client.get('/settings', follow_redirects=True)
    assert response.status_code == 200
    assert b"Login" in response.data
    assert b"Username" in response.data
    assert b"Password" in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_settings_update_email_success(mock_encryption_manager, mock_communication_module, client):
    """
    Test successful update of user email.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Prepare form data
    form_data = {
        'username': 'testuser',
        'email': 'newemail@example.com',
        'password': '',
        'confirm_password': ''
    }

    response = client.post('/settings', data=form_data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Profile updated successfully." in response.data

    # Verify that email was updated in the database
    with app.app_context():
        user = User.query.filter_by(username='testuser').first()
        assert user.email == 'newemail@example.com'

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_settings_update_password_success(mock_encryption_manager, mock_communication_module, client):
    """
    Test successful update of user password.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Prepare form data
    form_data = {
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'newsecurepassword',
        'confirm_password': 'newsecurepassword'
    }

    response = client.post('/settings', data=form_data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Profile updated successfully." in response.data

    # Verify that password was updated in the database
    with app.app_context():
        user = User.query.filter_by(username='testuser').first()
        assert user.check_password('newsecurepassword') is True

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_settings_update_password_mismatch(mock_encryption_manager, mock_communication_module, client):
    """
    Test that password and confirm_password must match.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Prepare form data with mismatched passwords
    form_data = {
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'newsecurepassword',
        'confirm_password': 'differentpassword'
    }

    response = client.post('/settings', data=form_data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Passwords do not match." in response.data

    # Verify that password was not updated in the database
    with app.app_context():
        user = User.query.filter_by(username='testuser').first()
        assert user.check_password('newsecurepassword') is False
        assert user.check_password('testpassword') is True

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_settings_update_invalid_email(mock_encryption_manager, mock_communication_module, client):
    """
    Test that updating with an invalid email address fails.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Prepare form data with invalid email
    form_data = {
        'username': 'testuser',
        'email': 'invalidemail',
        'password': '',
        'confirm_password': ''
    }

    response = client.post('/settings', data=form_data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Invalid email address." in response.data

    # Verify that email was not updated in the database
    with app.app_context():
        user = User.query.filter_by(username='testuser').first()
        assert user.email == 'test@example.com'

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_settings_csrf_protection(mock_encryption_manager, mock_communication_module, client):
    """
    Test that CSRF protection is active by attempting to submit the form without a CSRF token.
    """
    app.config['WTF_CSRF_ENABLED'] = True
    # Login first
    login(client, 'testuser', 'testpassword')

    # Prepare form data without CSRF token
    form_data = {
        'username': 'testuser',
        'email': 'newemail@example.com',
        'password': '',
        'confirm_password': ''
    }

    response = client.post('/settings', data=form_data, follow_redirects=True)
    assert response.status_code == 400
    assert b"The CSRF token is missing." in response.data
    app.config['WTF_CSRF_ENABLED'] = False
