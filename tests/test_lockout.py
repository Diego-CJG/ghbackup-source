"""Tests unitarios para ghbackup.auth.lockout."""
import time

import pytest

from ghbackup.auth.lockout import (
    MAX_ATTEMPTS,
    LOCKOUT_SECONDS,
    AttemptsWarning,
    LockoutError,
    check_lockout,
    failed_attempts,
    record_failure,
    record_success,
    remaining_attempts,
)


@pytest.fixture(autouse=True)
def patch_lockout_path(tmp_path, monkeypatch):
    """Redirige lockout.json a un directorio temporal para todos los tests."""
    lockout_file = tmp_path / "lockout.json"
    monkeypatch.setattr("ghbackup.auth.lockout._lockout_path", lambda: lockout_file)
    monkeypatch.setattr("ghbackup.state.paths.app_dir", lambda: tmp_path)


class TestCheckLockout:
    def test_no_lockout_by_default(self):
        check_lockout()  # no debe lanzar nada

    def test_lockout_active_raises(self, tmp_path, monkeypatch):
        import json
        lockout_file = tmp_path / "lockout.json"
        state = {"attempts": 0, "locked_until": time.time() + 60.0}
        lockout_file.write_text(json.dumps(state))
        monkeypatch.setattr("ghbackup.auth.lockout._lockout_path", lambda: lockout_file)
        with pytest.raises(LockoutError, match="Espera"):
            check_lockout()

    def test_expired_lockout_does_not_raise(self, tmp_path, monkeypatch):
        import json
        lockout_file = tmp_path / "lockout.json"
        state = {"attempts": 0, "locked_until": time.time() - 1.0}
        lockout_file.write_text(json.dumps(state))
        monkeypatch.setattr("ghbackup.auth.lockout._lockout_path", lambda: lockout_file)
        check_lockout()  # no debe lanzar nada


class TestRecordFailure:
    def test_first_failure_increments_counter(self):
        assert failed_attempts() == 0
        try:
            record_failure()
        except AttemptsWarning:
            pass
        assert failed_attempts() == 1

    def test_failures_accumulate(self):
        for _ in range(2):
            try:
                record_failure()
            except AttemptsWarning:
                pass
        assert failed_attempts() == 2

    def test_warning_raised_at_two_remaining(self):
        """Al quedar 2 intentos (intento 3 de 5), debe lanzar AttemptsWarning."""
        for _ in range(MAX_ATTEMPTS - 2 - 1):
            try:
                record_failure()
            except AttemptsWarning:
                pass
        with pytest.raises(AttemptsWarning, match="2 intento"):
            record_failure()

    def test_warning_raised_at_one_remaining(self):
        """Al quedar 1 intento (intento 4 de 5), debe lanzar AttemptsWarning."""
        for _ in range(MAX_ATTEMPTS - 2):
            try:
                record_failure()
            except AttemptsWarning:
                pass
        with pytest.raises(AttemptsWarning, match="1 intento"):
            record_failure()

    def test_lockout_raised_at_max_attempts(self):
        """Al llegar a 5 intentos, debe lanzar LockoutError."""
        for _ in range(MAX_ATTEMPTS - 1):
            try:
                record_failure()
            except AttemptsWarning:
                pass
        with pytest.raises(LockoutError):
            record_failure()

    def test_lockout_resets_counter(self):
        """Tras el lockout, el contador de intentos se resetea a 0."""
        for _ in range(MAX_ATTEMPTS - 1):
            try:
                record_failure()
            except AttemptsWarning:
                pass
        with pytest.raises(LockoutError):
            record_failure()
        assert failed_attempts() == 0


class TestRecordSuccess:
    def test_success_resets_counter(self):
        try:
            record_failure()
        except AttemptsWarning:
            pass
        assert failed_attempts() == 1
        record_success()
        assert failed_attempts() == 0

    def test_success_when_no_failures_no_error(self):
        record_success()  # no debe lanzar nada

    def test_success_removes_lockout_file(self, tmp_path, monkeypatch):
        lockout_file = tmp_path / "lockout.json"
        lockout_file.write_text("{}")
        monkeypatch.setattr("ghbackup.auth.lockout._lockout_path", lambda: lockout_file)
        record_success()
        assert not lockout_file.exists()


class TestRemainingAttempts:
    def test_full_remaining_at_start(self):
        assert remaining_attempts() == MAX_ATTEMPTS

    def test_decreases_after_failure(self):
        try:
            record_failure()
        except AttemptsWarning:
            pass
        assert remaining_attempts() == MAX_ATTEMPTS - 1

    def test_zero_when_locked(self, tmp_path, monkeypatch):
        import json
        lockout_file = tmp_path / "lockout.json"
        state = {"attempts": 0, "locked_until": time.time() + 60.0}
        lockout_file.write_text(json.dumps(state))
        monkeypatch.setattr("ghbackup.auth.lockout._lockout_path", lambda: lockout_file)
        assert remaining_attempts() == 0

    def test_resets_to_max_after_success(self):
        try:
            record_failure()
        except AttemptsWarning:
            pass
        record_success()
        assert remaining_attempts() == MAX_ATTEMPTS
