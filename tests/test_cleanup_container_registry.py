from cleanup_container_registry import main


def test_main_returns_zero():
    assert main() == 0
