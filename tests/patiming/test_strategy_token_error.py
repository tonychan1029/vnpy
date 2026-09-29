import pytest

from vnpy_patiming.mcp_service import _configured_strategy_token


def test_strategy_token_permission_error_is_actionable(tmp_path, monkeypatch):
    token_file = tmp_path / "selection_mcp_token"
    token_file.write_text("secret-token", encoding="utf-8")

    def deny_read(path, *args, **kwargs):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setenv("PATIMING_STRATEGY_MCP_TOKEN", "")
    monkeypatch.setenv("PATIMING_STRATEGY_MCP_TOKEN_FILE", str(token_file))
    monkeypatch.setattr("vnpy_patiming.mcp_service.Path.read_text", deny_read)

    with pytest.raises(RuntimeError) as raised:
        _configured_strategy_token()

    message = str(raised.value)
    assert str(token_file) in message
    assert "runner_uid=" in message
    assert "setfacl -m u:aiprj:r--" in message
    assert "secret-token" not in message
