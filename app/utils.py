DAY_ORDER = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
LEVEL_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]

ROLE_LABEL = {
    "admin": "Quản trị viên",
    "consultant": "Tư vấn viên",
    "teacher": "Giáo viên",
    "student": "Học viên",
}


def rank_for(average: float) -> str:
    if average >= 9:
        return "Xuất sắc"
    if average >= 8:
        return "Giỏi"
    if average >= 6.5:
        return "Khá"
    if average >= 5:
        return "Trung bình"
    return "Yếu"


def vnd(value) -> str:
    return f"{float(value or 0):,.0f}".replace(",", ".") + " đ"


def schedule_text(classroom) -> str:
    groups: dict = {}
    rows = sorted(classroom.schedules, key=lambda s: (DAY_ORDER.index(s.day_of_week), s.start_time))
    for s in rows:
        groups.setdefault((s.start_time, s.end_time), []).append(s.day_of_week)
    parts = [f"{', '.join(days)} ({st:%H:%M} - {et:%H:%M})" for (st, et), days in groups.items()]
    return "; ".join(parts) if parts else "Chưa có lịch"

import markdown as _md


def md_to_html(text: str) -> str:
    """Convert markdown đơn giản sang HTML an toàn."""
    if not text:
        return ""
    return _md.markdown(
        text,
        extensions=["nl2br", "sane_lists"],
        output_format="html",
    )