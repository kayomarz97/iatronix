"""Search history endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session as get_async_session
from app.schemas.auth import SearchHistoryItem

router = APIRouter(prefix="/history", tags=["history"])


def _get_authenticated_user(request: Request):
    """Extract current user from request state (set by ApiKeyAuthMiddleware)."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@router.get("", response_model=list[SearchHistoryItem])
async def get_history(
    request: Request,
    limit: int = Query(default=50, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_session),
):
    """Return the current user's search history, most recent first."""
    from app.models.search_history import SearchHistory

    user = _get_authenticated_user(request)

    result = await db.execute(
        select(SearchHistory)
        .where(SearchHistory.user_id == user.id)
        .order_by(SearchHistory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = result.scalars().all()
    return [
        SearchHistoryItem(
            id=item.id,
            query_text=item.query_text,
            query_type=item.query_type,
            response_summary=item.response_summary,
            created_at=item.created_at.isoformat() if item.created_at else "",
        )
        for item in items
    ]


@router.delete("/{item_id}")
async def delete_history_item(
    item_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a single search history entry."""
    from app.models.search_history import SearchHistory

    user = _get_authenticated_user(request)

    result = await db.execute(
        select(SearchHistory).where(
            SearchHistory.id == item_id,
            SearchHistory.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")
    await db.delete(item)
    await db.commit()
    return {"deleted": True}


@router.delete("")
async def clear_history(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
):
    """Delete all search history for the current user."""
    from app.models.search_history import SearchHistory

    user = _get_authenticated_user(request)
    await db.execute(delete(SearchHistory).where(SearchHistory.user_id == user.id))
    await db.commit()
    return {"cleared": True}
