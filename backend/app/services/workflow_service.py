from sqlalchemy.orm import Session
from ..models.status import Status
from ..models.transition import Transition
from ..models.request import Request
from fastapi import HTTPException, status

class WorkflowService:
    @staticmethod
    def validate_transition(db: Session, request: Request, new_status_id: int, user_role: str):
        transition = db.query(Transition).filter(
            Transition.from_status_id == request.status_id,
            Transition.to_status_id == new_status_id
        ).first()

        if not transition:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transition from status {request.status_id} to {new_status_id} is not allowed"
            )

        if transition.allowed_roles:
            allowed = [r.strip() for r in transition.allowed_roles.split(",") if r.strip()]
            if allowed and user_role not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{user_role}' cannot perform this transition"
                )

        return True
