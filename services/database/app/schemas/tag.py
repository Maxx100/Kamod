from uuid import UUID

from app.schemas.common import APIModel, SlugStr


class TagSummary(APIModel):
    slug: SlugStr
    name: str


class TagResponse(TagSummary):
    id: UUID
    group_code: str | None = None
    is_active: bool
