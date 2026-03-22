from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app.api.dependencies import TelegramServiceDep
from app.schemas.tg import (
    TelegramAttendanceAnswerRequest,
    TelegramClaimJobRequest,
    TelegramClaimJobResponse,
    TelegramCompleteJobRequest,
    TelegramDueJobResponse,
    TelegramDueJobsQuery,
    TelegramFailJobRequest,
    TelegramLinkStartRequest,
    TelegramLinkStartResponse,
    TelegramOperationResponse,
)


router = APIRouter(prefix="/tg", tags=["telegram"])


def get_due_jobs_query(
    from_at: Annotated[AwareDatetime, Query(alias="from")],
    to_at: Annotated[AwareDatetime, Query(alias="to")],
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> TelegramDueJobsQuery:
    return TelegramDueJobsQuery(
        from_at=from_at,
        to_at=to_at,
        limit=limit,
    )


@router.get("/jobs/due", response_model=list[TelegramDueJobResponse])
def list_due_jobs(
    service: TelegramServiceDep,
    params: Annotated[TelegramDueJobsQuery, Depends(get_due_jobs_query)],
) -> list[TelegramDueJobResponse]:
    return service.list_due_jobs(params)


@router.post("/jobs/{job_id}/claim", response_model=TelegramClaimJobResponse)
def claim_job(
    job_id: UUID,
    payload: TelegramClaimJobRequest,
    service: TelegramServiceDep,
) -> TelegramClaimJobResponse:
    return service.claim_job(job_id, payload)


@router.post("/jobs/{job_id}/complete", response_model=TelegramOperationResponse)
def complete_job(
    job_id: UUID,
    payload: TelegramCompleteJobRequest,
    service: TelegramServiceDep,
) -> TelegramOperationResponse:
    return service.complete_job(job_id, payload)


@router.post("/jobs/{job_id}/fail", response_model=TelegramOperationResponse)
def fail_job(
    job_id: UUID,
    payload: TelegramFailJobRequest,
    service: TelegramServiceDep,
) -> TelegramOperationResponse:
    return service.fail_job(job_id, payload)


@router.post("/attendance/answer", response_model=TelegramOperationResponse)
def save_attendance_answer(
    payload: TelegramAttendanceAnswerRequest,
    service: TelegramServiceDep,
) -> TelegramOperationResponse:
    return service.save_attendance_answer(payload)


@router.post("/link-start", response_model=TelegramLinkStartResponse)
def link_start(
    payload: TelegramLinkStartRequest,
    service: TelegramServiceDep,
) -> TelegramLinkStartResponse:
    return service.link_start(payload)
