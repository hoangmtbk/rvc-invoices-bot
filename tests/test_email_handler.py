from unittest.mock import MagicMock, patch
import pytest


def _make_mock_msg(uid, subject):
    msg = MagicMock()
    msg.uid = uid
    msg.subject = subject
    return msg


def test_fetch_filters_by_invoice_keywords():
    msgs = [
        _make_mock_msg("1", "Hóa đơn điện tử tháng 1"),
        _make_mock_msg("2", "Meeting reminder"),
        _make_mock_msg("3", "HDDT - Q1 invoice"),
        _make_mock_msg("4", "Gửi hóa đơn tháng 2"),
        _make_mock_msg("5", "Weekly report"),
    ]

    mock_mailbox = MagicMock()
    mock_mailbox.__enter__ = MagicMock(return_value=mock_mailbox)
    mock_mailbox.__exit__ = MagicMock(return_value=False)
    mock_mailbox.fetch.return_value = msgs
    mock_mailbox.login.return_value = mock_mailbox

    with patch("email_handler.MailBox", return_value=mock_mailbox):
        from email_handler import fetch_unseen_emails
        result = fetch_unseen_emails()

    assert len(result) == 3
    uids = [m.uid for m in result]
    assert "1" in uids
    assert "3" in uids
    assert "4" in uids
    assert "2" not in uids
    assert "5" not in uids


def test_fetch_raises_on_imap_failure():
    with patch("email_handler.MailBox", side_effect=ConnectionError("Connection refused")):
        from email_handler import fetch_unseen_emails
        with pytest.raises(ConnectionError):
            fetch_unseen_emails()


def test_mark_as_seen_calls_flag():
    mock_mailbox = MagicMock()
    mock_mailbox.__enter__ = MagicMock(return_value=mock_mailbox)
    mock_mailbox.__exit__ = MagicMock(return_value=False)
    mock_mailbox.login.return_value = mock_mailbox

    with patch("email_handler.MailBox", return_value=mock_mailbox):
        from email_handler import mark_as_seen
        mark_as_seen("42")

    mock_mailbox.flag.assert_called_once_with("42", ["\\Seen"], True)
