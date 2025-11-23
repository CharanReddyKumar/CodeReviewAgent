import json

import pytest

from src import app as app_module

client = app_module.app.test_client()


@pytest.mark.timeout(1)
def test_exec_rejects_sleep_commands():
    response = client.post("/exec", json={"cmd": "sleep 5"})
    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "blocked" in body


def test_inspect_blocks_traversal(tmp_path):
    sneaky_file = tmp_path / "../../etc/passwd"
    sneaky_file.write_text("root::0:0::/root:/bin/bash")
    response = client.get("/inspect/../../etc/passwd")
    payload = json.loads(response.get_data(as_text=True))
    assert "error" in payload and payload["error"] == "forbidden"
