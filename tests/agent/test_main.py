import pytest

from lifecycle_agent import host as main_module


class _FakeCredential:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeHost:
    def __init__(self) -> None:
        self.port: int | None = None

    def run(self, *, port: int) -> None:
        self.port = port


def test_main_uses_default_host_port_8088_when_port_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_credential = _FakeCredential()
    fake_host = _FakeHost()

    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(
        main_module,
        "DefaultAzureCredential",
        lambda: fake_credential,
    )
    monkeypatch.setattr(main_module, "_load_department_agent", lambda _credential: object())
    monkeypatch.setattr(main_module, "ResponsesHostServer", lambda _agent: fake_host)

    main_module.main()

    assert fake_host.port == 8088


def test_main_closes_runtime_credential_when_host_run_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_credential = _FakeCredential()

    monkeypatch.setattr(
        main_module,
        "DefaultAzureCredential",
        lambda: fake_credential,
    )
    monkeypatch.setattr(main_module, "_load_department_agent", lambda _credential: object())
    monkeypatch.setattr(main_module, "ResponsesHostServer", lambda _agent: _FakeHost())

    main_module.main()

    assert fake_credential.closed is True


def test_main_closes_runtime_credential_when_host_run_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_credential = _FakeCredential()

    class _RaisingHost:
        def run(self, *, port: int) -> None:
            raise RuntimeError(f"host failed on port {port}")

    monkeypatch.setattr(
        main_module,
        "DefaultAzureCredential",
        lambda: fake_credential,
    )
    monkeypatch.setattr(main_module, "_load_department_agent", lambda _credential: object())
    monkeypatch.setattr(main_module, "ResponsesHostServer", lambda _agent: _RaisingHost())

    with pytest.raises(RuntimeError, match="host failed"):
        main_module.main()

    assert fake_credential.closed is True
