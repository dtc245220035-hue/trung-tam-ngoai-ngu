from datetime import date, datetime
from calendar import monthrange

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import (Attendance, ClassRoom, Course, Enrollment, Invoice,
                     Payment, Result, Student, User)
from .web import render

router = APIRouter(prefix="/stats", tags=["stats"])

VALID_TABS = ("enrollment", "revenue", "completion")


def _parse_date(raw: str, default: date) -> date:
    raw = (raw or "").strip()
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return default


def _stats_enrollment(db: Session, start: date, end: date):
    """Sĩ số theo lớp — số HV đăng ký active trong kỳ."""
    rows = (db.query(ClassRoom)
            .join(Course, ClassRoom.course_id == Course.course_id)
            .order_by(ClassRoom.class_code).all())
    data = []
    for c in rows:
        n_new = (db.query(Enrollment)
                 .filter(Enrollment.class_id == c.class_id,
                         Enrollment.status == "active",
                         Enrollment.enroll_date >= datetime.combine(start, datetime.min.time()),
                         Enrollment.enroll_date <= datetime.combine(end, datetime.max.time()))
                 .count())
        data.append({
            "class_code": c.class_code,
            "course_name": c.course.course_name,
            "level": c.course.level,
            "room": c.room or "—",
            "current": c.current_students,
            "max": c.max_students,
            "n_new": n_new,
            "fill_rate": round(c.current_students / c.max_students * 100, 1) if c.max_students else 0,
        })
    return data


def _stats_revenue(db: Session, start: date, end: date):
    """Doanh thu theo tháng — tổng tiền thu từ Payment trong kỳ, gộp theo tháng."""
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    payments = (db.query(Payment)
                .filter(Payment.payment_date >= start_dt,
                        Payment.payment_date <= end_dt)
                .all())

    monthly: dict[str, dict] = {}
    for p in payments:
        key = p.payment_date.strftime("%Y-%m")
        m = monthly.setdefault(key, {"total": 0.0, "cash": 0.0, "transfer": 0.0, "n": 0})
        m["total"] += p.amount
        m["n"] += 1
        if p.method == "cash":
            m["cash"] += p.amount
        else:
            m["transfer"] += p.amount

    rows = [{"month": k, **v} for k, v in sorted(monthly.items())]

    # Tổng công nợ toàn hệ thống (không phụ thuộc filter)
    total_debt = db.query(
        func.coalesce(func.sum(Invoice.total_amount - Invoice.paid_amount), 0)
    ).scalar() or 0

    total_revenue = sum(r["total"] for r in rows)
    return rows, total_revenue, total_debt


def _stats_completion(db: Session):
    """Tỷ lệ hoàn thành khóa học = HV có điểm TB >= 5 / tổng HV đã có điểm."""
    rows = (db.query(ClassRoom)
            .join(Course, ClassRoom.course_id == Course.course_id)
            .order_by(ClassRoom.class_code).all())
    data = []
    for c in rows:
        results = db.query(Result).filter(Result.class_id == c.class_id).all()
        n_total = len(results)
        n_pass = sum(1 for r in results if r.average >= 5)
        rate = round(n_pass / n_total * 100, 1) if n_total else 0
        data.append({
            "class_code": c.class_code,
            "course_name": c.course.course_name,
            "level": c.course.level,
            "n_enrolled": c.current_students,
            "n_graded": n_total,
            "n_pass": n_pass,
            "n_fail": n_total - n_pass,
            "rate": rate,
        })
    return data


@router.get("")
def stats_home(request: Request,
               tab: str = "enrollment",
               from_date: str = "",
               to_date: str = "",
               user: User = Depends(require_roles("admin")),
               db: Session = Depends(get_db)):
    if tab not in VALID_TABS:
        tab = "enrollment"

    today = date.today()
    default_start = date(today.year, 1, 1)
    start = _parse_date(from_date, default_start)
    end = _parse_date(to_date, today)
    if start > end:
        start, end = end, start

    ctx = {"tab": tab, "from_date": start.isoformat(), "to_date": end.isoformat()}

    if tab == "enrollment":
        ctx["rows"] = _stats_enrollment(db, start, end)
        ctx["total_students"] = sum(r["current"] for r in ctx["rows"])
    elif tab == "revenue":
        rows, total_revenue, total_debt = _stats_revenue(db, start, end)
        ctx["rows"] = rows
        ctx["total_revenue"] = total_revenue
        ctx["total_debt"] = total_debt
    else:
        ctx["rows"] = _stats_completion(db)

    return render(request, "stats.html", user=user, **ctx)