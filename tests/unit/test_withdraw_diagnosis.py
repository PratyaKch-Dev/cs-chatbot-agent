"""Unit tests for withdrawal diagnosis rule engine."""

import pytest
from domain.withdraw_diagnosis import (
    diagnose_withdrawal_failure,
    WithdrawalFailureCase,
    _check_blocked,
    _check_blacklisted,
    _check_enrolled,
    _check_sync_pending,
)


class TestHelperFunctions:
    def test_check_blocked_suspended(self):
        assert _check_blocked({"status": "suspended"}) is True

    def test_check_blocked_active(self):
        assert _check_blocked({"status": "active"}) is False

    def test_check_blacklisted_true(self):
        assert _check_blacklisted({"blacklisted": True}) is True

    def test_check_blacklisted_false(self):
        assert _check_blacklisted({"blacklisted": False}) is False

    def test_check_enrolled_true(self):
        assert _check_enrolled({"enrolled": True}) is True

    def test_check_not_enrolled(self):
        assert _check_enrolled({"enrolled": False}) is False

    def test_sync_pending(self):
        assert _check_sync_pending({"sync_status": "pending"}) is True

    def test_sync_done(self):
        assert _check_sync_pending({"sync_status": "synced"}) is False


class TestDiagnoseWithdrawalFailure:
    def test_not_enrolled_case(self):
        # TODO Phase 6: implement
        pass

    def test_blacklisted_case(self):
        # TODO Phase 6: implement
        pass

    def test_sync_pending_case(self):
        # TODO Phase 6: implement
        pass
