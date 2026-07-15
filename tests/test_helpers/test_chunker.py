import pytest

from rbb_bot.utils.helpers import chunker


def test_chunker():
    """Test chunker function."""
    test_list = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    chunk_size = 3
    expected = [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10]]
    assert list(chunker(test_list, chunk_size)) == expected


def test_long_chunker():
    """Test chunker function."""
    test_list = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    chunk_size = 11
    expected = [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]]
    assert list(chunker(test_list, chunk_size)) == expected


def test_short_chunker():
    """Test chunker function."""
    test_list = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    chunk_size = 2
    expected = [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]]
    assert list(chunker(test_list, chunk_size)) == expected


def test_string_chunker():
    """Test chunker function."""
    test_list = ["12345678910"]
    chunk_size = 3
    expected = [["12345678910"]]
    assert list(chunker(test_list, chunk_size)) == expected


def test_long_string_chunker():
    """Test chunker function."""
    test_list = ["12345678910", "12345678910", "12345678910"]
    chunk_size = 2
    max_len_per_chunk = 15
    expected = [["12345678910"], ["12345678910"], ["12345678910"]]
    assert list(chunker(test_list, chunk_size, max_len_per_chunk)) == expected


def test_with_max_len_per_chunk():
    """Test chunker function."""
    test_list = ["12345678910", "12345678910", "12345678910"]
    chunk_size = 3
    max_len_per_chunk = 11
    expected = [["12345678910"], ["12345678910"], ["12345678910"]]
    assert list(chunker(test_list, chunk_size, max_len_per_chunk)) == expected


def test_exception():
    """Test chunker function."""
    test_list = ["12345678910", "12345678910", "12345678910"]
    chunk_size = 3
    max_len_per_chunk = 10
    with pytest.raises(ValueError):
        list(chunker(test_list, chunk_size, max_len_per_chunk))
