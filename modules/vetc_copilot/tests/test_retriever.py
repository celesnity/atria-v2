from retriever import Retriever

ROWS = [
    {"knowledge_id": "K001", "question": "Khi nào cần đăng kiểm xe", "answer": "", "topic": "Đăng kiểm"},
    {"knowledge_id": "K002", "question": "Bảo hiểm TNDS là gì", "answer": "", "topic": "Bảo hiểm"},
]


def test_search_ranks_relevant_first():
    hits = Retriever(ROWS).search("đăng kiểm khi nào", k=2)
    assert hits[0]["knowledge_id"] == "K001"
    assert hits[0]["_score"] > 0


def test_search_returns_nothing_for_unrelated():
    assert Retriever(ROWS).search("zzzz qqqq", k=2) == []
