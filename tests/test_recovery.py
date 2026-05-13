"""Tests unitarios para ghbackup.auth.recovery."""
import json
import pytest

from ghbackup.auth.recovery import (
    CODE_COUNT,
    CHARSET,
    GROUP_COUNT,
    GROUP_SIZE,
    codes_exist,
    delete_codes,
    generate_codes,
    normalize,
    remaining_count,
    save_codes,
    validate_and_consume,
)


@pytest.fixture(autouse=True)
def patch_recovery_path(tmp_path, monkeypatch):
    """Redirige recovery_codes.json a un directorio temporal para todos los tests."""
    rc_file = tmp_path / "recovery_codes.json"
    monkeypatch.setattr("ghbackup.auth.recovery.recovery_codes_path", lambda: rc_file)
    monkeypatch.setattr("ghbackup.state.paths.app_dir", lambda: tmp_path)
    return rc_file


class TestGenerateCodes:
    def test_generates_correct_count(self):
        codes = generate_codes()
        assert len(codes) == CODE_COUNT

    def test_correct_format(self):
        codes = generate_codes()
        for code in codes:
            parts = code.split("-")
            assert len(parts) == GROUP_COUNT, f"Esperado {GROUP_COUNT} grupos en: {code}"
            for part in parts:
                assert len(part) == GROUP_SIZE, f"Esperado {GROUP_SIZE} chars por grupo en: {part}"

    def test_only_valid_charset(self):
        codes = generate_codes()
        for code in codes:
            normalized = normalize(code)
            for ch in normalized:
                assert ch in CHARSET, f"Caracter invalido: {ch} en {code}"

    def test_codes_are_unique(self):
        codes = generate_codes()
        assert len(set(codes)) == CODE_COUNT, "Se generaron codigos duplicados"

    def test_multiple_generations_differ(self):
        batch1 = set(generate_codes())
        batch2 = set(generate_codes())
        # Es estadisticamente imposible que dos generaciones sean identicas
        assert batch1 != batch2

    def test_no_ambiguous_chars(self):
        """El charset no debe incluir 0, 1, I, O para evitar confusion visual."""
        for ch in "01IO":
            assert ch not in CHARSET


class TestNormalize:
    def test_removes_dashes(self):
        assert normalize("ABCDE-FGHIJ-KLMNO") == "ABCDEFGHIJKLMNO"

    def test_removes_spaces(self):
        assert normalize("ABCDE FGHIJ") == "ABCDEFGHIJ"

    def test_uppercase(self):
        assert normalize("abcde-fghij") == "ABCDEFGHIJ"

    def test_mixed_input(self):
        assert normalize("abc-DEF 123") == "ABCDEF123"


class TestSaveAndLoadCodes:
    def test_file_created_after_save(self, patch_recovery_path):
        codes = generate_codes()
        save_codes(codes)
        assert patch_recovery_path.exists()

    def test_file_contains_correct_count(self, patch_recovery_path):
        codes = generate_codes()
        save_codes(codes)
        data = json.loads(patch_recovery_path.read_text())
        assert len(data["codes"]) == CODE_COUNT

    def test_plain_text_not_stored(self, patch_recovery_path):
        codes = generate_codes()
        save_codes(codes)
        raw = patch_recovery_path.read_text()
        for code in codes:
            assert normalize(code) not in raw, "El codigo en texto plano no debe guardarse"

    def test_all_codes_initially_unused(self, patch_recovery_path):
        save_codes(generate_codes())
        data = json.loads(patch_recovery_path.read_text())
        assert all(not e["used"] for e in data["codes"])


class TestValidateAndConsume:
    def test_valid_code_returns_true(self):
        codes = generate_codes()
        save_codes(codes)
        assert validate_and_consume(codes[0]) is True

    def test_used_code_returns_false(self):
        codes = generate_codes()
        save_codes(codes)
        validate_and_consume(codes[0])
        assert validate_and_consume(codes[0]) is False

    def test_invalid_code_returns_false(self):
        save_codes(generate_codes())
        assert validate_and_consume("XXXXX-XXXXX-XXXXX-XXXXX-XXXXX") is False

    def test_code_without_dashes_valid(self):
        codes = generate_codes()
        save_codes(codes)
        # Ingresar sin guiones debe funcionar igual
        no_dashes = codes[1].replace("-", "")
        assert validate_and_consume(no_dashes) is True

    def test_code_lowercase_valid(self):
        codes = generate_codes()
        save_codes(codes)
        assert validate_and_consume(codes[2].lower()) is True

    def test_each_code_independent(self):
        codes = generate_codes()
        save_codes(codes)
        assert validate_and_consume(codes[0]) is True
        assert validate_and_consume(codes[1]) is True
        assert validate_and_consume(codes[2]) is True

    def test_no_file_returns_false(self):
        # Sin archivo guardado
        assert validate_and_consume("ANYCODE") is False

    def test_all_codes_consumable(self):
        codes = generate_codes()
        save_codes(codes)
        for code in codes:
            assert validate_and_consume(code) is True
        # Todos usados
        for code in codes:
            assert validate_and_consume(code) is False


class TestRemainingCount:
    def test_full_count_after_save(self):
        save_codes(generate_codes())
        assert remaining_count() == CODE_COUNT

    def test_decreases_after_consume(self):
        codes = generate_codes()
        save_codes(codes)
        validate_and_consume(codes[0])
        assert remaining_count() == CODE_COUNT - 1

    def test_zero_when_all_used(self):
        codes = generate_codes()
        save_codes(codes)
        for code in codes:
            validate_and_consume(code)
        assert remaining_count() == 0

    def test_zero_when_no_file(self):
        assert remaining_count() == 0


class TestCodesExistAndDelete:
    def test_false_before_save(self):
        assert not codes_exist()

    def test_true_after_save(self):
        save_codes(generate_codes())
        assert codes_exist()

    def test_delete_removes_file(self, patch_recovery_path):
        save_codes(generate_codes())
        assert patch_recovery_path.exists()
        delete_codes()
        assert not patch_recovery_path.exists()

    def test_delete_nonexistent_no_error(self):
        delete_codes()  # No debe lanzar excepcion
