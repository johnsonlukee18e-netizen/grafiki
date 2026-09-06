"""Employee CRUD. Colours are derived, never accepted from the client."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_db_session, require_manager
from app.models import AuditAction, Employee, User
from app.schemas import EmployeeCreate, EmployeeOut, EmployeeUpdate
from app.services import audit_service
from app.services.seniority import employee_color, seniority_label

router = APIRouter(prefix="/api/employees", tags=["employees"])


def to_out(employee: Employee, on_date: date | None = None) -> EmployeeOut:
    return EmployeeOut(
        id=employee.id,
        first_name=employee.first_name,
        last_name=employee.last_name,
        full_name=employee.full_name,
        role=employee.role,
        employment_date=employee.employment_date,
        active=employee.active,
        color=employee_color(employee.role, employee.employment_date, on_date),
        seniority_label=seniority_label(employee.employment_date, on_date),
        created_at=employee.created_at,
        updated_at=employee.updated_at,
    )


@router.get("", response_model=list[EmployeeOut])
def list_employees(
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_manager),
) -> list[EmployeeOut]:
    query = select(Employee).order_by(Employee.last_name, Employee.first_name)
    if not include_inactive:
        query = query.where(Employee.active.is_(True))
    return [to_out(e) for e in db.scalars(query)]


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeCreate,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> EmployeeOut:
    employee = Employee(**payload.model_dump())
    db.add(employee)
    db.flush()
    audit_service.record(
        db,
        AuditAction.EMPLOYEE_CREATED,
        user=user,
        entity_type="employee",
        entity_id=employee.id,
        metadata={"name": employee.full_name, "role": employee.role.value},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(employee)
    return to_out(employee)


def _require_employee(db: Session, employee_id: int) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono pracownika.")
    return employee


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db_session),
    _: User = Depends(require_manager),
) -> EmployeeOut:
    return to_out(_require_employee(db, employee_id))


@router.put("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> EmployeeOut:
    employee = _require_employee(db, employee_id)
    changes = payload.model_dump(exclude_unset=True)
    was_active = employee.active
    for field, value in changes.items():
        setattr(employee, field, value)
    db.flush()
    action = (
        AuditAction.EMPLOYEE_DEACTIVATED
        if was_active and employee.active is False
        else AuditAction.EMPLOYEE_UPDATED
    )
    audit_service.record(
        db,
        action,
        user=user,
        entity_type="employee",
        entity_id=employee.id,
        metadata={"changes": {k: str(v) for k, v in changes.items()}},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(employee)
    return to_out(employee)


@router.delete("/{employee_id}", response_model=EmployeeOut)
def deactivate_employee(
    employee_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> EmployeeOut:
    """Soft delete: rosters and the audit trail must keep referring to the person."""
    employee = _require_employee(db, employee_id)
    employee.active = False
    db.flush()
    audit_service.record(
        db,
        AuditAction.EMPLOYEE_DEACTIVATED,
        user=user,
        entity_type="employee",
        entity_id=employee.id,
        metadata={"name": employee.full_name},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(employee)
    return to_out(employee)
