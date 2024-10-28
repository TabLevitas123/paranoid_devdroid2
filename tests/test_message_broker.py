# tests/test_message_broker.py

"""
Unit Tests for MessageBroker

This module contains comprehensive unit tests for the MessageBroker class,
ensuring robust functionality, error handling, and security compliance.
"""

import pytest
import threading
import time
from unittest.mock import MagicMock, patch

from modules.communication.message_broker import MessageBroker, MessageBrokerError
from modules.utilities.logging_manager import setup_logging


@pytest.fixture
def message_broker():
    mb = MessageBroker()
    yield mb


def test_publish_and_consume_message(message_broker):
    """
    Test publishing a message to an agent and consuming it successfully.
    """
    message = {
        'message_id': 'msg_001',
        'timestamp': time.time(),
        'sender_id': 'agent_1',
        'receiver_id': 'agent_2',
        'message_type': 'task',
        'content': "encrypted_{'action': 'process_data'}"
    }
    message_broker.publish_message("agent_2", message)
    consumed_message = message_broker.consume_message("agent_2", timeout=5)
    assert consumed_message == message


def test_consume_message_timeout(message_broker):
    """
    Test consuming a message with a timeout when no message is available.
    """
    consumed_message = message_broker.consume_message("agent_3", timeout=1)
    assert consumed_message is None


def test_publish_message_failure(message_broker):
    """
    Test handling failure when publishing a message.
    """
    with patch.object(message_broker, 'agent_queues', side_effect=Exception("Queue creation failed")):
        with pytest.raises(MessageBrokerError) as exc_info:
            message_broker.publish_message("agent_4", {})
        assert "Failed to publish message" in str(exc_info.value)


def test_consume_message_failure(message_broker):
    """
    Test handling failure when consuming a message.
    """
    with patch.object(message_broker, 'agent_queues', side_effect=Exception("Queue access failed")):
        with pytest.raises(MessageBrokerError) as exc_info:
            message_broker.consume_message("agent_5")
        assert "Failed to consume message" in str(exc_info.value)


def test_broadcast_message_success(message_broker):
    """
    Test publishing and consuming a broadcast message.
    """
    broadcast_message = {
        'message_id': 'msg_broadcast_001',
        'timestamp': time.time(),
        'sender_id': 'agent_admin',
        'receiver_id': 'ALL',
        'message_type': 'announcement',
        'content': "encrypted_{'info': 'System will reboot at midnight.'}"
    }
    message_broker.publish_broadcast(broadcast_message)
    consumed_message = message_broker.consume_broadcast("agent_6")
    assert consumed_message == broadcast_message


def test_broadcast_message_no_message(message_broker):
    """
    Test consuming a broadcast message when no broadcast message is available.
    """
    consumed_message = message_broker.consume_broadcast("agent_7")
    assert consumed_message is None


def test_create_group_success(message_broker):
    """
    Test creating a group successfully.
    """
    group_id = "group_1"
    members = ["agent_a", "agent_b"]
    message_broker.create_group(group_id, members)
    assert group_id in message_broker.group_queues
    assert message_broker.group_queues[group_id]['members'] == set(members)


def test_create_group_already_exists(message_broker):
    """
    Test creating a group that already exists.
    """
    group_id = "group_2"
    members = ["agent_c", "agent_d"]
    message_broker.create_group(group_id, members)
    with patch.object(message_broker.logger, 'warning') as mock_logger_warning:
        message_broker.create_group(group_id, members)
        mock_logger_warning.assert_called_with(f"Group {group_id} already exists.")


def test_publish_group_message_success(message_broker):
    """
    Test publishing a message to a group successfully.
    """
    group_id = "group_3"
    members = ["agent_e", "agent_f"]
    message_broker.create_group(group_id, members)
    group_message = {
        'message_id': 'msg_group_001',
        'timestamp': time.time(),
        'sender_id': 'agent_8',
        'receiver_id': group_id,
        'message_type': 'group_task',
        'content': "encrypted_{'action': 'group_analysis'}"
    }
    message_broker.publish_group_message(group_id, group_message)
    consumed_message_e = message_broker.consume_group_message(group_id, "agent_e")
    consumed_message_f = message_broker.consume_group_message(group_id, "agent_f")
    assert consumed_message_e == group_message
    assert consumed_message_f == group_message


def test_publish_group_message_nonexistent_group(message_broker):
    """
    Test publishing a message to a group that does not exist.
    """
    group_id = "group_nonexistent"
    group_message = {
        'message_id': 'msg_group_002',
        'timestamp': time.time(),
        'sender_id': 'agent_9',
        'receiver_id': group_id,
        'message_type': 'group_task',
        'content': "encrypted_{'action': 'group_report'}"
    }
    with patch.object(message_broker.logger, 'warning') as mock_logger_warning:
        message_broker.publish_group_message(group_id, group_message)
        mock_logger_warning.assert_called_with(f"Group {group_id} does not exist.")


def test_consume_group_message_non_member(message_broker):
    """
    Test consuming a group message by an agent that is not a member of the group.
    """
    group_id = "group_4"
    members = ["agent_g", "agent_h"]
    message_broker.create_group(group_id, members)
    group_message = {
        'message_id': 'msg_group_003',
        'timestamp': time.time(),
        'sender_id': 'agent_10',
        'receiver_id': group_id,
        'message_type': 'group_task',
        'content': "encrypted_{'action': 'group_upgrade'}"
    }
    message_broker.publish_group_message(group_id, group_message)
    consumed_message = message_broker.consume_group_message(group_id, "agent_i")
    assert consumed_message is None


def test_consume_group_message_no_message(message_broker):
    """
    Test consuming a group message when no group message is available.
    """
    group_id = "group_5"
    members = ["agent_j"]
    message_broker.create_group(group_id, members)
    consumed_message = message_broker.consume_group_message(group_id, "agent_j")
    assert consumed_message is None
