# tests/Test_communication_module.py

"""
Unit Tests for CommunicationModule

This module contains comprehensive unit tests for the CommunicationModule class,
ensuring robust functionality, error handling, and security compliance.
"""

import pytest
import threading
import time
from unittest.mock import MagicMock, patch

from modules.communication.communication_module import CommunicationModule, CommunicationModuleError
from modules.security.encryption_manager import EncryptionManager
from modules.communication.message_broker import MessageBroker
from modules.utilities.logging_manager import setup_logging


@pytest.fixture
def mock_encryption_manager():
    with patch('modules.communication.communication_module.EncryptionManager') as mock_enc:
        instance = mock_enc.return_value
        instance.encrypt_data = MagicMock(side_effect=lambda x: f"encrypted_{x}")
        instance.decrypt_data = MagicMock(side_effect=lambda x: x.replace("encrypted_", ""))
        yield instance


@pytest.fixture
def mock_message_broker():
    with patch('modules.communication.communication_module.MessageBroker') as mock_mb:
        instance = mock_mb.return_value
        instance.publish_message = MagicMock()
        instance.consume_message = MagicMock(return_value=None)
        instance.publish_broadcast = MagicMock()
        instance.consume_broadcast = MagicMock(return_value=None)
        instance.create_group = MagicMock()
        instance.publish_group_message = MagicMock()
        instance.consume_group_message = MagicMock(return_value=None)
        yield instance


@pytest.fixture
def communication_module(mock_encryption_manager, mock_message_broker):
    cm = CommunicationModule()
    yield cm


def test_send_message_success(communication_module, mock_encryption_manager, mock_message_broker):
    """
    Test successful sending of a message.
    """
    communication_module.send_message(
        sender_id="agent_1",
        receiver_id="agent_2",
        message_type="task",
        content={"action": "generate_text", "data": "Hello, World!"}
    )
    mock_encryption_manager.encrypt_data.assert_called_once_with({"action": "generate_text", "data": "Hello, World!"})
    assert mock_message_broker.publish_message.call_count == 1
    args, kwargs = mock_message_broker.publish_message.call_args
    receiver_id_arg, message_arg = args
    assert receiver_id_arg == "agent_2"
    assert message_arg['sender_id'] == "agent_1"
    assert message_arg['receiver_id'] == "agent_2"
    assert message_arg['message_type'] == "task"
    assert message_arg['content'] == "encrypted_{'action': 'generate_text', 'data': 'Hello, World!'}"


def test_send_message_failure(communication_module, mock_encryption_manager, mock_message_broker):
    """
    Test handling of failure when sending a message.
    """
    mock_message_broker.publish_message.side_effect = Exception("Publish failed")
    with pytest.raises(CommunicationModuleError) as exc_info:
        communication_module.send_message(
            sender_id="agent_1",
            receiver_id="agent_2",
            message_type="task",
            content={"action": "generate_text", "data": "Hello, World!"}
        )
    assert "Failed to send message" in str(exc_info.value)


def test_receive_message_success(communication_module, mock_encryption_manager, mock_message_broker):
    """
    Test successful receiving of a message.
    """
    mock_message = {
        'message_id': 'msg_123',
        'timestamp': time.time(),
        'sender_id': 'agent_1',
        'receiver_id': 'agent_2',
        'message_type': 'task',
        'content': "encrypted_{'action': 'generate_text', 'data': 'Hello, World!'}"
    }
    mock_message_broker.consume_message.return_value = mock_message

    message = communication_module.receive_message(
        receiver_id="agent_2",
        message_type_filter="task",
        timeout=5
    )

    mock_message_broker.consume_message.assert_called_once_with("agent_2", 5)
    mock_encryption_manager.decrypt_data.assert_called_once_with("encrypted_{'action': 'generate_text', 'data': 'Hello, World!'}")
    assert message['content'] == "{'action': 'generate_text', 'data': 'Hello, World!'}"


def test_receive_message_type_filter(communication_module, mock_encryption_manager, mock_message_broker):
    """
    Test receiving a message with type filtering.
    """
    mock_message = {
        'message_id': 'msg_124',
        'timestamp': time.time(),
        'sender_id': 'agent_1',
        'receiver_id': 'agent_2',
        'message_type': 'notification',
        'content': "encrypted_{'info': 'System update available.'}"
    }
    mock_message_broker.consume_message.return_value = mock_message

    message = communication_module.receive_message(
        receiver_id="agent_2",
        message_type_filter="task",
        timeout=5
    )

    mock_encryption_manager.decrypt_data.assert_not_called()
    assert message is None


def test_receive_message_timeout(communication_module, mock_encryption_manager, mock_message_broker):
    """
    Test receiving a message when no message is available (timeout).
    """
    mock_message_broker.consume_message.return_value = None

    message = communication_module.receive_message(
        receiver_id="agent_2",
        message_type_filter="task",
        timeout=1
    )

    mock_encryption_manager.decrypt_data.assert_not_called()
    assert message is None


def test_register_listener_success(communication_module):
    """
    Test successful registration of a listener.
    """
    callback = MagicMock()
    communication_module.register_listener("agent_2", callback)
    assert "agent_2" in communication_module.listeners
    assert isinstance(communication_module.listener_threads["agent_2"], threading.Thread)


def test_register_listener_already_registered(communication_module):
    """
    Test registering a listener for an agent that already has a listener.
    """
    callback = MagicMock()
    communication_module.register_listener("agent_3", callback)
    communication_module.register_listener("agent_3", callback)
    # Listener should not be duplicated
    assert "agent_3" in communication_module.listeners
    assert communication_module.listener_threads["agent_3"].is_alive()


def test_unregister_listener_success(communication_module):
    """
    Test successful unregistration of a listener.
    """
    callback = MagicMock()
    communication_module.register_listener("agent_4", callback)
    communication_module.unregister_listener("agent_4")
    assert "agent_4" not in communication_module.listeners
    assert "agent_4" not in communication_module.listener_threads


def test_unregister_listener_not_registered(communication_module):
    """
    Test unregistration of a listener that does not exist.
    """
    communication_module.unregister_listener("agent_5")
    # Should log a warning but not raise an exception


def test_broadcast_message_success(communication_module, mock_encryption_manager, mock_message_broker):
    """
    Test successful sending of a broadcast message.
    """
    communication_module.broadcast_message(
        sender_id="agent_1",
        message_type="announcement",
        content={"message": "System maintenance at midnight."}
    )
    mock_encryption_manager.encrypt_data.assert_called_once_with({"message": "System maintenance at midnight."})
    mock_message_broker.publish_broadcast.assert_called_once()
    args, kwargs = mock_message_broker.publish_broadcast.call_args
    message_arg = args[0]
    assert message_arg['sender_id'] == "agent_1"
    assert message_arg['receiver_id'] == "ALL"
    assert message_arg['message_type'] == "announcement"
    assert message_arg['content'] == "encrypted_{'message': 'System maintenance at midnight.'}"


def test_broadcast_message_failure(communication_module, mock_encryption_manager, mock_message_broker):
    """
    Test handling of failure when sending a broadcast message.
    """
    mock_message_broker.publish_broadcast.side_effect = Exception("Broadcast failed")
    with pytest.raises(CommunicationModuleError) as exc_info:
        communication_module.broadcast_message(
            sender_id="agent_1",
            message_type="announcement",
            content={"message": "System maintenance at midnight."}
        )
    assert "Failed to send broadcast message" in str(exc_info.value)


def test_shutdown(communication_module):
    """
    Test shutting down the CommunicationModule gracefully.
    """
    communication_module.running = True
    communication_module.register_listener("agent_6", MagicMock())
    communication_module.shutdown()
    assert not communication_module.running
    assert "agent_6" not in communication_module.listeners
    assert "agent_6" not in communication_module.listener_threads
