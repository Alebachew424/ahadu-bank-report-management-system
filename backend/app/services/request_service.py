from sqlalchemy.orm import Session
from ..models.request import Request
from ..models.status import Status
from ..models.user import User
from ..schemas.request import RequestCreate, RequestUpdate
from fastapi import HTTPException, status as http_status


class RequestService:

    @staticmethod
    def create_request(db: Session, data: RequestCreate, requester_id: int) -> Request:
        """
        New ticket always starts at 'Pending Dept Approval' and is tied to
        the requester's department so the right manager sees it.
        """
        requester = db.query(User).filter(User.id == requester_id).one()
        if not requester.department_id:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Your account is not linked to a department. Contact an administrator.",
            )

        pending = db.query(Status).filter(
            Status.name == "Pending Dept Approval",
            Status.is_active.is_(True),
        ).first()
        if not pending:
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Workflow is not configured. Run the seed script.",
            )

        new_req = Request(
            title=data.title,
            description=data.description,
            request_type_id=data.request_type_id,
            priority=data.priority,
            due_date=data.due_date,
            additional_data=data.additional_data or {},
            requester_id=requester_id,
            department_id=requester.department_id,
            status_id=pending.id,
        )
        db.add(new_req)
        db.commit()
        db.refresh(new_req)
        return new_req

    @staticmethod
    def get_request(db: Session, request_id: int, user: User) -> Request:
        req = db.query(Request).filter(Request.id == request_id).first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")

        role_name = user.role.name if user.role else "Requester"

        # MIS team and admins can see everything
        if user.is_superuser or role_name in {
            "MIS Officer", "MIS Manager", "MIS Supervisor", "Admin", "System Administrator"
        }:
            return req

        # Dept manager can see requests from their own department only
        if user.role and user.role.role_type == "Manager" and role_name == "Requester Manager":
            if user.department_id != req.department_id:
                raise HTTPException(
                    status_code=403,
                    detail="You cannot view requests from another department",
                )
            return req

        # Regular requester can only see their own tickets
        if req.requester_id != user.id:
            raise HTTPException(status_code=403, detail="You cannot view this request")

        return req

    @staticmethod
    def update_request(db: Session, request_id: int, data: RequestUpdate, user: User) -> Request:
        req = RequestService.get_request(db, request_id, user)
        role_name = user.role.name if user.role else "Requester"

        # Only the requester (or MIS team) can edit
        if req.requester_id != user.id and not user.is_superuser and role_name not in {
            "MIS Officer", "MIS Manager", "MIS Supervisor", "Admin", "System Administrator"
        }:
            raise HTTPException(status_code=403, detail="Only the requester can edit this request")

        # Requester can only edit while in early stages
        if req.requester_id == user.id and req.status and req.status.name not in {
            "Pending Dept Approval", "Rejected"
        }:
            raise HTTPException(
                status_code=400,
                detail="Tickets can only be edited while pending department approval or after rejection",
            )

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(req, field, value)
        db.commit()
        db.refresh(req)
        return req

    @staticmethod
    def assign_request(db: Session, request_id: int, analyst_id: int) -> Request:
        req = db.query(Request).filter(Request.id == request_id).first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        analyst = db.query(User).filter(User.id == analyst_id).first()
        if not analyst:
            raise HTTPException(status_code=404, detail="MIS Officer not found")

        role_name = analyst.role.name if analyst.role else ""
        if role_name not in {"MIS Officer", "MIS Analyst", "MIS Supervisor", "Admin", "System Administrator"}:
            raise HTTPException(status_code=400, detail="The selected user is not an MIS Officer")

        req.assigned_to_id = analyst_id

        # Auto-advance status from Submitted → Assigned
        submitted = db.query(Status).filter(Status.name == "Submitted").first()
        assigned  = db.query(Status).filter(Status.name == "Assigned").first()
        if submitted and assigned and req.status_id == submitted.id:
            req.status_id = assigned.id

        db.commit()
        db.refresh(req)
        return req
