from openarm_data_collection.cli import main


def test_setup_can_dry_run(capsys):
    assert main(["setup-can", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "openarm-can-cli can_configure" in output
    assert "openarm-can-cli -i can0 set_zero --arm" in output
    assert "openarm-can-cli -i can1 set_zero --arm" in output
