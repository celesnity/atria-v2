def test_scripts_dir_importable():
    import sys

    assert any(p.endswith("scripts") and "vetc_copilot" in p for p in sys.path)
