from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import Facility, User
from .web import flash, render

router = APIRouter(prefix="/facilities", tags=["facilities"])

VALID_TYPES = ("room", "equipment")
VALID_STATUS = ("active", "broken", "disposed")


def _next_code(db: Session) -> str:
    n = db.query(Facility).count() + 1
    while db.query(Facility).filter(Facility.facility_code == f"CS{n:04d}").first():
        n += 1
    return f"CS{n:04d}"


def _parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _validate(name: str, ftype: str, qty: str, price: str,
              status: str) -> list[str]:
    errors = []
    if not name or len(name.strip()) < 3:
        errors.append("Tên cơ sở vật chất phải có ít nhất 3 ký tự")
    if ftype not in VALID_TYPES:
        errors.append("Loại phải là 'Phòng' hoặc 'Thiết bị'")
    if status not in VALID_STATUS:
        errors.append("Trạng thái không hợp lệ")
    try:
        q = int(qty)
        if q <= 0:
            errors.append("Số lượng phải lớn hơn 0")
    except (ValueError, TypeError):
        errors.append("Số lượng không hợp lệ")
    try:
        p = float(price)
        if p < 0:
            errors.append("Đơn giá phải >= 0")
    except (ValueError, TypeError):
        errors.append("Đơn giá không hợp lệ")
    return errors


@router.get("")
def list_facilities(request: Request,
                    q: str = "",
                    ftype: str = "",
                    status: str = "",
                    user: User = Depends(require_roles("admin")),
                    db: Session = Depends(get_db)):
    query = db.query(Facility)

    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Facility.facility_code.ilike(like),
            Facility.facility_name.ilike(like),
            Facility.room.ilike(like),
        ))
    if ftype in VALID_TYPES:
        query = query.filter(Facility.facility_type == ftype)
    if status in VALID_STATUS:
        query = query.filter(Facility.status == status)

    facilities = query.order_by(Facility.facility_code).all()

    total_rooms = sum(f.quantity for f in facilities if f.facility_type == "room")
    total_equipment = sum(f.quantity for f in facilities if f.facility_type == "equipment")
    total_value = sum(f.total_value for f in facilities)

    return render(request, "facilities_list.html", user=user,
                  facilities=facilities, q=q, ftype=ftype, status=status,
                  total_rooms=total_rooms, total_equipment=total_equipment,
                  total_value=total_value)


@router.get("/new")
def new_form(request: Request,
             user: User = Depends(require_roles("admin"))):
    return render(request, "facility_form.html", user=user,
                  mode="new", form={})


@router.post("/new")
def create_facility(request: Request,
                    facility_name: str = Form(""),
                    facility_type: str = Form("equipment"),
                    room: str = Form(""),
                    quantity: str = Form("1"),
                    unit_price: str = Form("0"),
                    purchase_date: str = Form(""),
                    status: str = Form("active"),
                    note: str = Form(""),
                    user: User = Depends(require_roles("admin")),
                    db: Session = Depends(get_db)):
    facility_name = facility_name.strip()
    room = room.strip()
    note = note.strip()

    form = {"facility_name": facility_name, "facility_type": facility_type,
            "room": room, "quantity": quantity, "unit_price": unit_price,
            "purchase_date": purchase_date, "status": status, "note": note}

    errors = _validate(facility_name, facility_type, quantity, unit_price, status)
    if errors:
        return render(request, "facility_form.html", user=user,
                      mode="new", form=form,
                      error="; ".join(errors), status_code=400)

    f = Facility(
        facility_code=_next_code(db),
        facility_name=facility_name,
        facility_type=facility_type,
        room=room or None,
        quantity=int(quantity),
        unit_price=float(unit_price),
        purchase_date=_parse_date(purchase_date),
        status=status,
        note=note or None,
    )
    db.add(f)
    db.commit()

    flash(request, f"Đã thêm {facility_name} ({f.facility_code})")
    return RedirectResponse("/facilities", status_code=303)


@router.get("/{facility_id}/edit")
def edit_form(facility_id: int,
              request: Request,
              user: User = Depends(require_roles("admin")),
              db: Session = Depends(get_db)):
    f = db.get(Facility, facility_id)
    if not f:
        return render(request, "404.html", user=user, status_code=404)

    form = {
        "facility_name": f.facility_name,
        "facility_type": f.facility_type,
        "room": f.room or "",
        "quantity": f.quantity,
        "unit_price": f"{f.unit_price:.0f}",
        "purchase_date": f.purchase_date.isoformat() if f.purchase_date else "",
        "status": f.status,
        "note": f.note or "",
    }
    return render(request, "facility_form.html", user=user,
                  mode="edit", facility=f, form=form)


@router.post("/{facility_id}/edit")
def update_facility(facility_id: int,
                    request: Request,
                    facility_name: str = Form(""),
                    facility_type: str = Form("equipment"),
                    room: str = Form(""),
                    quantity: str = Form("1"),
                    unit_price: str = Form("0"),
                    purchase_date: str = Form(""),
                    status: str = Form("active"),
                    note: str = Form(""),
                    user: User = Depends(require_roles("admin")),
                    db: Session = Depends(get_db)):
    f = db.get(Facility, facility_id)
    if not f:
        return render(request, "404.html", user=user, status_code=404)

    facility_name = facility_name.strip()
    room = room.strip()
    note = note.strip()

    form = {"facility_name": facility_name, "facility_type": facility_type,
            "room": room, "quantity": quantity, "unit_price": unit_price,
            "purchase_date": purchase_date, "status": status, "note": note}

    errors = _validate(facility_name, facility_type, quantity, unit_price, status)
    if errors:
        return render(request, "facility_form.html", user=user,
                      mode="edit", facility=f, form=form,
                      error="; ".join(errors), status_code=400)

    f.facility_name = facility_name
    f.facility_type = facility_type
    f.room = room or None
    f.quantity = int(quantity)
    f.unit_price = float(unit_price)
    f.purchase_date = _parse_date(purchase_date)
    f.status = status
    f.note = note or None
    db.commit()

    flash(request, f"Đã cập nhật {facility_name}")
    return RedirectResponse("/facilities", status_code=303)


@router.post("/{facility_id}/delete")
def delete_facility(facility_id: int,
                    request: Request,
                    user: User = Depends(require_roles("admin")),
                    db: Session = Depends(get_db)):
    f = db.get(Facility, facility_id)
    if not f:
        return render(request, "404.html", user=user, status_code=404)

    name = f.facility_name
    db.delete(f)
    db.commit()
    flash(request, f"Đã xóa {name}")
    return RedirectResponse("/facilities", status_code=303)