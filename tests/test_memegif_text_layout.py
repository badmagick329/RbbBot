from rbb_bot.memegifs.memegen import split_word, text_to_lines, text_to_words


def test_split_word():
    word = "ABC1ABC2ABC3ABC4ABC5ABC6ABC7ABC8"

    assert split_word(word, 8) == [
        "ABC1ABC2",
        "ABC3ABC4",
        "ABC5ABC6",
        "ABC7ABC8",
    ]


def test_text_to_words():
    text = "ABC1ABC2ABC3ABC4ABC5ABC6ABC7ABC8 ABC1 ABC2"

    assert text_to_words(text, 8) == [
        "ABC1ABC2",
        "ABC3ABC4",
        "ABC5ABC6",
        "ABC7ABC8",
        "ABC1",
        "ABC2",
    ]


def test_text_to_lines_keeps_text_within_limit_on_one_line():
    text = "ABC1ABC2ABC3ABC4ABC5ABC6ABC7ABC8"

    assert text_to_lines(text, 32) == [text]


def test_text_to_lines_wraps_at_word_boundary():
    text = "ABC1 ABC2 ABC3 ABC4 ABC5 ABC6 ABC7 ABC8"

    assert text_to_lines(text, 32) == [
        "ABC1 ABC2 ABC3 ABC4 ABC5 ABC6",
        "ABC7 ABC8",
    ]


def test_text_to_lines_normalises_whitespace():
    text = "ABC1   ABC2 ABC3 ABC4    ABC5      ABC6 ABC7 ABC8   "

    assert text_to_lines(text, 32) == [
        "ABC1 ABC2 ABC3 ABC4 ABC5 ABC6",
        "ABC7 ABC8",
    ]


def test_text_to_lines_returns_no_lines_for_empty_text():
    assert text_to_lines("", 32) == []


def test_text_to_lines_preserves_unicode_characters():
    text = "ABC1ABC2ABC3ABC4ABC5ABC6ABC7ABC8 🤔"

    assert text_to_lines(text, 32) == [
        "ABC1ABC2ABC3ABC4ABC5ABC6ABC7ABC8",
        "🤔",
    ]
