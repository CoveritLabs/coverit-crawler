from src.crawler.session.sequence_builders import sequence_description


def test_sequence_description_empty_sequence():
    assert sequence_description([]) == ""
