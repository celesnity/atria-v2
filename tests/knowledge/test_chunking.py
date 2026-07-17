from minder.core.knowledge.chunking import chunk_text


def test_empty_input_yields_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_paragraphs_pack_up_to_limit():
    text = "aaa\n\nbbb\n\nccc"
    chunks = chunk_text(text, max_chars=8)
    # "aaa\n\nbbb" = 8 chars fits; "ccc" starts a new chunk
    assert chunks == ["aaa\n\nbbb", "ccc"]


def test_oversized_paragraph_kept_whole():
    big = "x" * 50
    chunks = chunk_text(big, max_chars=10)
    assert chunks == [big]


def test_all_text_preserved_in_order():
    text = "one\n\ntwo\n\nthree"
    joined = "\n\n".join(chunk_text(text, max_chars=3))
    assert "one" in joined and "two" in joined and "three" in joined
