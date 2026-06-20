def test_ctk_root_fixture_is_usable(ctk_root):
    assert ctk_root.winfo_exists()
