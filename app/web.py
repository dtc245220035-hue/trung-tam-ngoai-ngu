from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .utils import ROLE_LABEL, md_to_html, schedule_text, vnd

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["vnd"] = vnd
templates.env.filters["md"] = md_to_html
templates.env.globals["schedule_text"] = schedule_text
templates.env.globals["ROLE_LABEL"] = ROLE_LABEL

BUILT = {"dashboard", "students", "courses", "classes", "teachers",
         "enroll", "invoices", "attendance", "results", "my_results",
         "my_classes", "my_schedule", "my_invoices", "lookup", "stats",
         "ai_advice", "ai_exercise", "ai_progress",
         "facilities", "salaries", "policies"}


def _m(key, label, path=None):
    return {"key": key, "label": label, "path": path or f"/{key}"}


MENU = {
    "admin": [
        _m("dashboard", "Tổng quan"),
        _m("accounts", "Tài khoản"),
        _m("students", "Học viên"),
        _m("courses", "Khóa học"),
        _m("classes", "Lớp và lịch học"),
        _m("teachers", "Giáo viên"),
        _m("invoices", "Học phí"),
        _m("facilities", "Cơ sở vật chất"),
        _m("salaries", "Lương giáo viên"),
        _m("policies", "Chính sách ưu đãi"),
        _m("lookup", "Tra cứu"),
        _m("stats", "Thống kê báo cáo"),
    ],
    "consultant": [
        _m("dashboard", "Tổng quan"),
        _m("students", "Học viên"),
        _m("enroll", "Đăng ký học"),
        _m("invoices", "Học phí"),
        _m("lookup", "Tra cứu"),
        _m("ai_advice", "AI tư vấn lớp", "/ai/advice"),
    ],
    "teacher": [
        _m("dashboard", "Tổng quan"),
        _m("my_classes", "Lớp của tôi"),
        _m("attendance", "Điểm danh"),
        _m("results", "Kết quả học tập"),
        _m("ai_exercise", "AI sinh bài luyện tập", "/ai/exercise"),
        _m("lookup", "Tra cứu"),
    ],
    "student": [
        _m("dashboard", "Tổng quan"),
        _m("my_schedule", "Lịch học"),
        _m("my_results", "Kết quả học tập"),
        _m("my_invoices", "Học phí"),
        _m("ai_exercise", "Bài luyện tập AI", "/ai/exercise"),
        _m("ai_progress", "Tóm tắt tiến độ", "/ai/progress"),
    ],
}


def flash(request: Request, message: str, kind: str = "ok") -> None:
    request.session.setdefault("flashes", [])
    request.session["flashes"] = request.session["flashes"] + [[kind, message]]


def render(request: Request, name: str, user=None, status_code: int = 200, **ctx):
    flashes = request.session.pop("flashes", []) if "session" in request.scope else []
    ctx.update(
        user=user,
        menu=MENU.get(user.role, []) if user else [],
        built=BUILT,
        flashes=flashes,
        current_path=request.url.path,
    )
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)