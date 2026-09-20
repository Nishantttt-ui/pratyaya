"""User store for the prototype.

This is an in-memory repository seeded at startup. It is deliberately behind an
interface so that swapping it for a database-backed implementation is a
one-class change: nothing in the routers knows where a user record lives.

No credential is hardcoded. Passwords come from the environment, and when they
are absent in local mode a random one is generated per process and printed once
to the console. A reviewer can therefore run the service immediately without
the repository ever containing a working password.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from backend.app.core.security import Role, hash_password, verify_password


@dataclass(frozen=True)
class User:
    username: str
    hashed_password: str
    role: Role


class UserRepository:
    """Lookup and credential verification for service accounts."""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    def add(self, username: str, password: str, role: Role) -> None:
        self._users[username] = User(
            username=username, hashed_password=hash_password(password), role=role
        )

    def get(self, username: str) -> User | None:
        return self._users.get(username)

    def authenticate(self, username: str, password: str) -> User | None:
        """Return the user when the password matches, otherwise None.

        The password is verified even when the username is unknown, against a
        dummy hash, so that response timing does not reveal which usernames
        exist.
        """
        user = self._users.get(username)
        if user is None:
            verify_password(password, hash_password("dummy-to-equalise-timing"))
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user


def seed_demo_users(settings) -> tuple[UserRepository, dict[str, str]]:
    """Build the repository, returning it with any generated passwords.

    Generated passwords are returned rather than logged from here, so that the
    caller decides whether printing them is appropriate for the environment.
    """
    repository = UserRepository()
    generated: dict[str, str] = {}

    for username, role, configured in (
        ("underwriter", Role.UNDERWRITER, settings.demo_underwriter_password),
        ("applicant", Role.APPLICANT, settings.demo_applicant_password),
    ):
        if configured is not None:
            password = configured.get_secret_value()
        else:
            password = secrets.token_urlsafe(12)
            generated[username] = password
        repository.add(username, password, role)

    return repository, generated
