"""Unit tests for monthly report: status classification, payload shape, webhook dispatch.

Covers ``Report._classify_status``, ``Report._check_site``, and
``send_report_to_webhook`` via mocked ``requests.post``. No real S3 or network.
"""

from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest
import requests as req

from classes.report import Report
from lib.notifications.webhook import send_report_to_webhook


INTERVAL_ERR = "backup interval is not same as set in site configuration"
SIZE_ERR_PREFIX = "backup size is same at "


class TestClassifyStatus:
    def test_completed_no_errors_no_failed_logs(self):
        r = Report()
        assert r._classify_status([], []) == "completed"

    def test_failed_when_interval_error(self):
        r = Report()
        errors = [INTERVAL_ERR]
        assert r._classify_status(errors, []) == "failed"

    def test_failed_when_failed_logs(self):
        r = Report()
        assert r._classify_status([], ["log entry"]) == "failed"

    def test_failed_when_both_interval_and_failed_logs(self):
        r = Report()
        errors = [INTERVAL_ERR, "backup size is same at some/key"]
        assert r._classify_status(errors, ["log entry"]) == "failed"

    def test_no_change_when_only_size_errors(self):
        r = Report()
        errors = ["backup size is same at some/key"]
        assert r._classify_status(errors, []) == "no_change"

    def test_no_change_when_mixed_size_errors(self):
        r = Report()
        errors = [
            "backup size is same at key1",
            "backup size is same at key2",
        ]
        assert r._classify_status(errors, []) == "no_change"

    def test_failed_when_mixed_interval_and_size_errors(self):
        r = Report()
        errors = [INTERVAL_ERR, "backup size is same at some/key"]
        assert r._classify_status(errors, []) == "failed"


class TestCheckSite:
    def _backup(self, key, size, timestamp):
        return {"Key": key, "Size": size, "LastModified": timestamp}

    def test_no_errors_when_backups_match_interval_and_different_sizes(self):
        r = Report()
        # difference_in_days uses date().day subtraction, so day 2 - day 1 = 1
        backups = [
            self._backup("site/db/2026-01-02/dump.sql", 200, Mock(timestamp=lambda: 86400 * 2)),
            self._backup("site/db/2026-01-01/dump.sql", 100, Mock(timestamp=lambda: 86400)),
        ]
        site = {"name": "site", "options": {"interval": 1}}
        assert r._check_site(backups, 1, site, "sql") == []

    def test_interval_mismatch_error(self):
        r = Report()
        backups = [
            self._backup("site/db/2026-01-01/dump.sql", 100, Mock(timestamp=lambda: 1000)),
            self._backup("site/db/2026-01-05/dump.sql", 200, Mock(timestamp=lambda: 5000)),
        ]
        site = {"name": "site", "options": {"interval": 1}}
        errors = r._check_site(backups, 1, site, "sql")
        assert any(INTERVAL_ERR in e for e in errors)

    def test_size_same_error(self):
        r = Report()
        backups = [
            self._backup("site/db/2026-01-01/dump.sql", 100, Mock(timestamp=lambda: 1000)),
            self._backup("site/db/2026-01-02/dump.sql", 100, Mock(timestamp=lambda: 2000)),
        ]
        site = {"name": "site", "options": {"interval": 1}}
        errors = r._check_site(backups, 1, site, "sql")
        assert any("backup size is same at" in e for e in errors)

    def test_mixed_returns_both_errors(self):
        r = Report()
        backups = [
            self._backup("site/db/2026-01-01/dump.sql", 100, Mock(timestamp=lambda: 1000)),
            self._backup("site/db/2026-01-05/dump.sql", 100, Mock(timestamp=lambda: 5000)),
        ]
        site = {"name": "site", "options": {"interval": 1}}
        errors = r._check_site(backups, 1, site, "sql")
        assert any(INTERVAL_ERR in e for e in errors)
        assert any("backup size is same at" in e for e in errors)

    def test_single_backup_no_error(self):
        r = Report()
        backups = [
            self._backup("site/db/2026-01-01/dump.sql", 100, Mock(timestamp=lambda: 1000)),
        ]
        site = {"name": "site", "options": {"interval": 1}}
        assert r._check_site(backups, 1, site, "sql") == []

    def test_empty_backups_no_error(self):
        r = Report()
        site = {"name": "site", "options": {"interval": 1}}
        assert r._check_site([], 1, site, "sql") == []




@contextmanager
def webhook_test_config(**values):
    cfg = Mock()
    defaults = {
        "webhook_url": "https://webhook.example.com/webhook",
        "enabled": "1",
        "channel": "webhook",
    }
    merged = {**defaults, **values}
    cfg.read.side_effect = (
        lambda section, key, default=None, print_error=True: merged.get(key, default)
    )
    with patch("lib.notifications.webhook.Config", return_value=cfg), \
         patch("lib.notifications.webhook.req.post") as mock_post:
        yield mock_post


class TestSendReportTowebhook:
    def test_payload_structure(self):
        with webhook_test_config() as mock_post:
            mock_post.return_value.raise_for_status = Mock()

            payload = {
                "report_type": "monthly",
                "storage": "test-storage",
                "month": "July_2026",
                "server_ip": "1.2.3.4",
                "version": "1.11.1",
                "total_size_bytes": 5000,
                "largest_site": {"name": "site-a", "size_bytes": 3000},
                "total_sites_in_config": 3,
                "data": [
                    {
                        "site": "site-a",
                        "status": "completed",
                        "in_config": True,
                        "errors": [],
                        "fail_count": 0,
                        "failed_logs": [],
                    },
                    {
                        "site": "site-b",
                        "status": "no_change",
                        "in_config": True,
                        "errors": ["backup size is same at site-b/key"],
                        "fail_count": 0,
                        "failed_logs": [],
                    },
                    {
                        "site": "site-c",
                        "status": "failed",
                        "in_config": False,
                        "errors": [INTERVAL_ERR],
                        "fail_count": 2,
                        "failed_logs": ["err1 (01-July-2026 12:00:00)"],
                    },
                ],
            }

            send_report_to_webhook(payload)

            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert kwargs["json"]["report_type"] == "monthly"
            assert len(kwargs["json"]["data"]) == 3
            for item in kwargs["json"]["data"]:
                assert "site" in item
                assert "status" in item
                assert "in_config" in item
                assert "errors" in item
                assert "fail_count" in item
                assert "failed_logs" in item

    def test_handles_http_error_gracefully(self):
        with webhook_test_config() as mock_post:
            mock_post.return_value.raise_for_status.side_effect = req.HTTPError("500 Server Error")

            # Should not raise exception (caught internally)
            send_report_to_webhook({"report_type": "monthly"})
            mock_post.assert_called_once()

    def test_skips_when_no_url(self):
        with webhook_test_config(webhook_url=None) as mock_post:
            send_report_to_webhook({"report_type": "monthly"})
            mock_post.assert_not_called()

    def test_in_config_flag_sites_in_storage_but_not_in_config(self):
        with webhook_test_config() as mock_post:
            mock_post.return_value.raise_for_status = Mock()

            payload = {
                "report_type": "monthly",
                "data": [
                    {"site": "known-site", "in_config": True, "status": "completed", "errors": [], "fail_count": 0, "failed_logs": []},
                    {"site": "orphan-site", "in_config": False, "status": "completed", "errors": [], "fail_count": 0, "failed_logs": []},
                ],
            }

            send_report_to_webhook(payload)
            data = mock_post.call_args.kwargs["json"]["data"]
            assert data[0]["in_config"] is True
            assert data[1]["in_config"] is False

