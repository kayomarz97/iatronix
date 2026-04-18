from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User

async def get_or_create_user(session: AsyncSession, uid: str, email: str | None) -> User:
    """Idempotent user provisioning from Firebase UID."""
    result = await session.execute(select(User).where(User.firebase_uid == uid))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(firebase_uid=uid, email=email)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
    return user
