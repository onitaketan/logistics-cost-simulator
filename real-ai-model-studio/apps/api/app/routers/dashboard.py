"""Dashboard KPIs (docs/02 §4).

Read-only aggregates for the dashboard. Compliance logic stays in services; this
router only surfaces derived counts/lists the UI renders. Backlog item P1-007
"Contract expiry alerts": surface contracts nearing their end date so operators
can renew or stop generation before rights lapse.
"""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.model import Model, ModelContract
from app.schemas.common import ok

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/expiring-contracts")
def expiring_contracts(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.MODEL_VIEW))],
    days: int = 30,
):
    """Contracts whose contract_end falls within [today, today+days] (inclusive).

    `days` is clamped to 1..365. Ordered by soonest expiry first so the most
    urgent renewals surface at the top.
    """
    days = max(1, min(days, 365))
    today = date.today()
    horizon = today + timedelta(days=days)
    stmt = (
        select(ModelContract, Model.stage_name)
        .join(Model, Model.id == ModelContract.model_id)
        .where(ModelContract.contract_end >= today)
        .where(ModelContract.contract_end <= horizon)
        .order_by(ModelContract.contract_end.asc())
    )
    rows = db.execute(stmt).all()
    return ok([
        {
            "contract_id": str(c.id),
            "model_id": str(c.model_id),
            "stage_name": stage_name,
            "contract_number": c.contract_number,
            "contract_end": str(c.contract_end),
            "days_left": (c.contract_end - today).days,
        }
        for c, stage_name in rows
    ])
