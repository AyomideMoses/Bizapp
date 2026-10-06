from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/expenses", tags=["Expenses"])

@router.post("/", response_model=schemas.ExpenseOut)
def create_expense(data: schemas.ExpenseCreate, db: Session = Depends(get_db)):
    values = data.model_dump(exclude_none=True)
    expense = models.Expense(**values)
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense

@router.get("/", response_model=list[schemas.ExpenseOut])
def list_expenses(
    category: str = "",
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Expense)
    if category:
        q = q.filter(models.Expense.category == category)
    if start:
        q = q.filter(models.Expense.expense_date >= start)
    if end:
        q = q.filter(models.Expense.expense_date <= end)
    return q.order_by(models.Expense.expense_date.desc()).all()

@router.get("/summary")
def expense_summary(db: Session = Depends(get_db)):
    rows = (
        db.query(models.Expense.category, func.sum(models.Expense.amount))
        .group_by(models.Expense.category)
        .all()
    )
    by_category = {cat: total for cat, total in rows}
    return {"total": sum(by_category.values()), "by_category": by_category}

@router.delete("/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.get(models.Expense, expense_id)
    if not expense:
        raise HTTPException(404, "Expense not found")
    db.delete(expense)
    db.commit()
    return {"deleted": expense_id}