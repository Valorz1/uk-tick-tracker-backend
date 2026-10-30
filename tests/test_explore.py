from scratch.explore import count_duplicate_ids


def test_count_duplicate_ids():
    records = [
        {"id": "abc"},
        {"id": "def"},
        {"id": "abc"},
    ]

    assert count_duplicate_ids(records) == 1