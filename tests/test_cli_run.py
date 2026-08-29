from semaphore_ui import cli


class FakeClient:
    def find_project(self, name):
        assert name == "configuration_management"
        return {"id": 1, "name": name}

    def find_template(self, project_id, name):
        assert project_id == 1
        assert name == "hello_world"
        return {"id": 7, "project_id": 1, "name": name}

    def create_task(self, project_id, template_id, variables):
        assert (project_id, template_id) == (1, 7)
        assert variables == {"target": "hermes-001.iot.home", "fact": "firewall_interface"}
        return {"id": 4, "status": "waiting"}


def test_run_command_resolves_names_and_passes_variables(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_client", lambda insecure=False: FakeClient())

    result = cli.main(
        [
            "run",
            "--project",
            "configuration_management",
            "--template",
            "hello_world",
            "--var",
            "target=hermes-001.iot.home",
            "--var",
            "fact=firewall_interface",
            "--json",
        ]
    )

    assert result == 0
    assert '"id": 4' in capsys.readouterr().out
