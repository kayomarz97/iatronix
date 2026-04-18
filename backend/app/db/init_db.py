from sqlalchemy import text

from app.db.session import engine


from app.models.base import CacheBase

async def check_db_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        async with engine.begin() as conn:
            await conn.run_sync(CacheBase.metadata.create_all)
        return True
    except Exception:
        return False
