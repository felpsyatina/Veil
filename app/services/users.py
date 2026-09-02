"""Работа с пользователями: получение/создание по Telegram ID, бан, рефералы."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.utils.security import generate_referral_code


async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_by_referral_code(session: AsyncSession, code: str) -> User | None:
    result = await session.execute(select(User).where(User.referral_code == code))
    return result.scalar_one_or_none()


async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_or_create_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    full_name: str | None,
    referrer_code: str | None = None,
) -> tuple[User, bool]:
    """Возвращает (пользователь, создан_ли_новый). Обновляет username/full_name при изменении."""
    user = await get_by_telegram_id(session, telegram_id)
    if user is not None:
        changed = False
        if user.username != username:
            user.username = username
            changed = True
        if user.full_name != full_name:
            user.full_name = full_name
            changed = True
        if changed:
            await session.flush()
        return user, False

    referrer: User | None = None
    if referrer_code:
        referrer = await get_by_referral_code(session, referrer_code)

    # Коллизии реферального кода крайне маловероятны (token_urlsafe), но на
    # всякий случай пробуем несколько раз перед тем, как сдаться.
    for _ in range(5):
        try:
            user = User(
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
                referrer_id=referrer.id if referrer else None,
                referral_code=generate_referral_code(),
            )
            session.add(user)
            await session.flush()
            return user, True
        except IntegrityError:
            await session.rollback()
    raise RuntimeError("Не удалось сгенерировать уникальный referral_code за 5 попыток")


async def set_banned(session: AsyncSession, user: User, banned: bool) -> None:
    user.is_banned = banned
    await session.flush()


async def mark_trial_used(session: AsyncSession, user: User) -> None:
    user.trial_used = True
    await session.flush()


async def find_by_query(session: AsyncSession, query: str) -> User | None:
    """Поиск пользователя админом: по числовому Telegram ID или по @username."""
    query = query.strip().lstrip("@")
    if query.isdigit():
        return await get_by_telegram_id(session, int(query))
    result = await session.execute(select(User).where(User.username.ilike(query)))
    return result.scalar_one_or_none()


async def count_referred(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(User).where(User.referrer_id == user_id)
    )
    return int(result.scalar_one())


async def list_all_telegram_ids(session: AsyncSession, *, exclude_banned: bool = True) -> list[int]:
    stmt = select(User.telegram_id)
    if exclude_banned:
        stmt = stmt.where(User.is_banned.is_(False))
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]
