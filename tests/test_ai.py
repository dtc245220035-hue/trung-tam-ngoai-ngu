"""Test module AI (yêu cầu đề bài)."""
import pytest

from app.ai import (
    EXERCISE_TOPICS,
    _fallback_advice,
    _fallback_exercise,
    _fallback_progress,
    _parse_exercise_json,
)


# ============ TC-AI-01: Fallback tư vấn lớp ============
def test_fallback_advice_empty_classes():
    text = _fallback_advice("A1", "Thứ 2 tối", [])
    assert isinstance(text, str)
    assert len(text) > 0


# ============ TC-AI-02: Fallback sinh bài tập ============
def test_fallback_exercise_returns_list():
    result = _fallback_exercise("Ngữ pháp", "A1", 5)
    assert isinstance(result, list)
    assert len(result) >= 3  # dataset có 3 câu Ngữ pháp


def test_fallback_exercise_structure():
    result = _fallback_exercise("Từ vựng", "A1", 3)
    for item in result:
        assert "q" in item and "opts" in item and "ans" in item
        assert item["ans"] in item["opts"]
        assert len(item["opts"]) == 4


# ============ TC-AI-03: Parse JSON hợp lệ ============
def test_parse_json_valid():
    text = '''[
        {"question": "Q1", "options": ["A", "B", "C", "D"],
         "correct_answer": "A", "explanation": "..."},
        {"question": "Q2", "options": ["A", "B", "C", "D"],
         "correct_answer": "B", "explanation": "..."}
    ]'''
    result = _parse_exercise_json(text)
    assert result is not None
    assert len(result) == 2
    assert result[0]["correct_answer"] == "A"


def test_parse_json_with_markdown():
    """AI thường bọc JSON trong ```json ... ```."""
    text = (
        "Đây là bài tập:\n"
        "```json\n"
        '[{"question": "Q1", "options": ["A", "B"], '
        '"correct_answer": "A", "explanation": "x"}]\n'
        "```\n"
        "Chúc bạn học tốt!"
    )
    result = _parse_exercise_json(text)
    assert result is not None
    assert len(result) == 1


def test_parse_json_invalid():
    assert _parse_exercise_json("") is None
    assert _parse_exercise_json("not json") is None
    assert _parse_exercise_json("[{invalid}]") is None


def test_parse_json_wrong_structure():
    """JSON đúng nhưng thiếu field."""
    text = '[{"question": "Q1"}]'
    assert _parse_exercise_json(text) is None


# ============ TC-AI-04: Route AI yêu cầu login + đúng role ============
def test_ai_advice_requires_consultant(client):
    """Chưa login → redirect về /login."""
    r = client.get("/ai/advice", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers.get("location", "")


def test_ai_advice_wrong_role(hv_client):
    """HV truy cập /ai/advice → 403."""
    r = hv_client.get("/ai/advice", follow_redirects=False)
    assert r.status_code == 403


def test_ai_advice_page_ok(tvv_client):
    """TVV truy cập /ai/advice → 200."""
    r = tvv_client.get("/ai/advice")
    assert r.status_code == 200
    assert "AI tư vấn lớp" in r.text


def test_ai_exercise_page_ok(hv_client):
    """HV truy cập /ai/exercise → 200."""
    r = hv_client.get("/ai/exercise")
    assert r.status_code == 200
    assert "AI sinh bài luyện tập" in r.text


def test_ai_progress_page_ok(hv_client):
    """HV truy cập /ai/progress → 200."""
    r = hv_client.get("/ai/progress")
    assert r.status_code == 200


# ============ TC-AI-05: Gọi AI sinh bài tập khi không có key → fallback ============
def test_ai_exercise_fallback(hv_client):
    """Do conftest tắt GEMINI_API_KEY → phải dùng fallback."""
    r = hv_client.post("/ai/exercise", data={
        "topic": "Từ vựng",
        "level": "A1",
        "num": 5,
    })
    assert r.status_code == 200
    assert "AI không phản hồi" in r.text or "phương án" in r.text.lower()