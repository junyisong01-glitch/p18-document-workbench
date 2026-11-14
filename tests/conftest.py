"""Scoped legacy-launcher test harness isolation, no business changes."""
import pytest
@pytest.fixture(autouse=True)
def legacy_mock_launcher_environment(request,monkeypatch):
    if request.node.name=='test_launcher_reuses_healthy_server':
        # This original test mocks ROOT/runtime; it never spawns a service.
        monkeypatch.delenv('P18_DATA_DIR',raising=False)
