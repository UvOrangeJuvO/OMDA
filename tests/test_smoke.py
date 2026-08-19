"""Smoke test: package imports and pytest collection works."""


def test_package_importable() -> None:
    import omda  # noqa: F401

    assert omda.__version__ == "0.1.0"
