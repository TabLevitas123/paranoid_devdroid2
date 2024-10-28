# tests/test_notifications.py

"""
Unit Tests for Notifications Page

This module contains comprehensive unit tests for the notifications.html template,
ensuring that user notifications are displayed correctly and adhere to security best practices.
"""

import pytest
from flask import url_for
from unittest.mock import patch, MagicMock
from flask_testing import TestCase
from __init__ import app, db, User, Notification

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
            # Add sample notifications
            notif1 = Notification(user_id=user.id, title='Welcome!', message='Welcome to Marvin Agent System.', read=False, timestamp='2021-12-01 09:00:00')
            notif2 = Notification(user_id=user.id, title='Update Available', message='A new update is available.', read=True, timestamp='2021-12-01 10:00:00')
            db.session.add_all([notif1, notif2])
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
def test_notifications_page_access_authenticated(mock_encryption_manager, mock_communication_module, client):
    """
    Test that authenticated users can access the notifications page.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    response = client.get('/notifications')
    assert response.status_code == 200
    assert b"Notifications" in response.data
    assert b"Welcome!" in response.data
    assert b"Update Available" in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_notifications_page_access_unauthenticated(mock_encryption_manager, mock_communication_module, client):
    """
    Test that unauthenticated users cannot access the notifications page.
    """
    response = client.get('/notifications', follow_redirects=True)
    assert response.status_code == 200
    assert b"Login" in response.data
    assert b"Username" in response.data
    assert b"Password" in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_notifications_display_unread(mock_encryption_manager, mock_communication_module, client):
    """
    Test that unread notifications are highlighted appropriately.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    response = client.get('/notifications')
    assert response.status_code == 200
    assert b"list-group-item-warning" in response.data  # Highlight for unread notifications
    assert b"Welcome!" in response.data
    assert b"Unread" in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_notifications_display_read(mock_encryption_manager, mock_communication_module, client):
    """
    Test that read notifications are displayed without highlights.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    response = client.get('/notifications')
    assert response.status_code == 200
    assert b"list-group-item-warning" not in response.data  # No highlight for read notifications
    assert b"Update Available" in response.data
    assert b"Read" in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_notifications_no_notifications(mock_encryption_manager, mock_communication_module, client):
    """
    Test that appropriate message is displayed when there are no notifications.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Remove all notifications
    with app.app_context():
        Notification.query.filter_by(user_id=1).delete()
        db.session.commit()

    response = client.get('/notifications')
    assert response.status_code == 200
    assert b"You have no notifications at this time." in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_notifications_mark_as_read(mock_encryption_manager, mock_communication_module, client):
    """
    Test that users can mark notifications as read.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Simulate marking a notification as read via an API endpoint (assuming such an endpoint exists)
    with patch('modules.communication.communication_module.CommunicationModule') as mock_comm_module:
        response = client.post('/notifications/mark_as_read', json={'notification_id': 1})
        assert response.status_code == 200
        assert b"Notification marked as read." in response.data

        # Verify that the notification is now read in the database
        with app.app_context():
            notif = Notification.query.get(1)
            assert notif.read is True

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_notifications_invalid_mark_as_read(mock_encryption_manager, mock_communication_module, client):
    """
    Test handling of invalid notification IDs when marking as read.
    """
    # Login first
    login(client, 'testuser', 'testpassword')

    # Attempt to mark a non-existent notification as read
    response = client.post('/notifications/mark_as_read', json={'notification_id': 999})
    assert response.status_code == 404
    assert b"Notification not found." in response.data

@patch('modules.communication.communication_module.CommunicationModule')
@patch('modules.security.encryption_manager.EncryptionManager')
def test_notifications_csrf_protection(mock_encryption_manager, mock_communication_module, client):
    """
    Test that CSRF protection is active by attempting to mark a notification as read without a CSRF token.
    """
    app.config['WTF_CSRF_ENABLED'] = True
    # Login first
    login(client, 'testuser', 'testpassword')

    # Attempt to mark a notification as read without CSRF token
    response = client.post('/notifications/mark_as_read', json={'notification_id': 1})
    assert response.status_code == 400
    assert b"The CSRF token is missing." in response.data
    app.config['WTF_CSRF_ENABLED'] = False
