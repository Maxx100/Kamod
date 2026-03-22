from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Select, and_, distinct, func, not_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Event, Tag
from app.models.enums import EventStatus
from app.schemas.event import CreatedEventsQueryParams, EventListQueryParams


class EventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, event: Event) -> None:
        self.session.add(event)

    def get_by_id(self, event_id: UUID) -> Event | None:
        stmt = (
            select(Event)
            .where(
                Event.id == event_id,
                Event.deleted_at.is_(None),
            )
            .options(
                selectinload(Event.creator),
                selectinload(Event.tags),
            )
        )
        return self.session.scalar(stmt)

    def get_for_update(self, event_id: UUID) -> Event | None:
        stmt = (
            select(Event)
            .where(
                Event.id == event_id,
                Event.deleted_at.is_(None),
            )
            .options(
                selectinload(Event.creator),
                selectinload(Event.tags),
            )
            .with_for_update()
        )
        return self.session.scalar(stmt)

    def list_public(self, params: EventListQueryParams) -> tuple[list[Event], int]:
        stmt = (
            select(Event)
            .where(Event.deleted_at.is_(None))
            .options(
                selectinload(Event.creator),
                selectinload(Event.tags),
            )
        )
        count_stmt = select(func.count(distinct(Event.id))).select_from(Event).where(Event.deleted_at.is_(None))

        stmt = self._apply_filters(stmt, params)
        count_stmt = self._apply_filters(count_stmt, params)

        events = list(
            self.session.scalars(
                stmt.order_by(Event.event_start_at.asc(), Event.id.asc())
                .limit(params.limit)
                .offset(params.offset)
            ).all()
        )
        total = self.session.scalar(count_stmt) or 0
        return events, total

    def list_created_by_user(
        self,
        user_id: UUID,
        params: CreatedEventsQueryParams,
    ) -> tuple[list[Event], int]:
        filters = [
            Event.created_by_user_id == user_id,
            Event.deleted_at.is_(None),
        ]
        if params.status is not None:
            filters.append(Event.status == params.status)

        stmt = (
            select(Event)
            .where(*filters)
            .options(
                selectinload(Event.creator),
                selectinload(Event.tags),
            )
            .order_by(Event.created_at.desc(), Event.id.desc())
            .limit(params.limit)
            .offset(params.offset)
        )
        count_stmt = select(func.count(Event.id)).where(*filters)

        events = list(self.session.scalars(stmt).all())
        total = self.session.scalar(count_stmt) or 0
        return events, total

    def _apply_filters(self, stmt: Select, params: EventListQueryParams) -> Select:
        requested_tags = params.tags
        if requested_tags:
            matching_event_ids = (
                select(Event.id)
                .join(Event.tags)
                .where(
                    Tag.slug.in_(requested_tags),
                    Tag.is_active.is_(True),
                    Event.deleted_at.is_(None),
                )
                .group_by(Event.id)
                .having(func.count(distinct(Tag.id)) == len(requested_tags))
            )
            stmt = stmt.where(Event.id.in_(matching_event_ids))

        if params.status is None:
            stmt = stmt.where(Event.status == EventStatus.PUBLISHED)
        else:
            stmt = stmt.where(Event.status == params.status)

        if params.created_by_user_id is not None:
            stmt = stmt.where(Event.created_by_user_id == params.created_by_user_id)

        if params.format is not None:
            stmt = stmt.where(Event.format == params.format)

        if params.is_free is not None:
            if params.is_free:
                stmt = stmt.where(Event.price_minor == 0)
            else:
                stmt = stmt.where(Event.price_minor > 0)

        if params.starts_from is not None:
            stmt = stmt.where(Event.event_start_at >= params.starts_from)

        if params.starts_to is not None:
            stmt = stmt.where(Event.event_start_at <= params.starts_to)

        if params.registration_open is not None:
            now = datetime.now(timezone.utc)
            registration_open_condition = and_(
                Event.status == EventStatus.PUBLISHED,
                Event.registration_start_at <= now,
                Event.registration_end_at >= now,
            )
            stmt = stmt.where(
                registration_open_condition if params.registration_open else not_(registration_open_condition)
            )

        return stmt
