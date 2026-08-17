"""Namespace-aware UUID allocation for M02."""

from __future__ import annotations

from uuid import UUID

from .contracts import IdentityNamespace, ScopedIdentity


class IdentityConflictError(ValueError):
    """Raised when a UUID is reused with incompatible semantics."""


class UnknownIdentityError(KeyError):
    """Raised when a UUID is not present in the registry."""


class IdentityRegistry:
    """In-process reference registry for globally unique scoped identities."""

    def __init__(self) -> None:
        self._identities: dict[UUID, ScopedIdentity] = {}

    def issue(
        self,
        namespace: IdentityNamespace,
        *,
        household_id: UUID | None = None,
    ) -> ScopedIdentity:
        identity = ScopedIdentity(namespace=namespace, household_id=household_id)
        self.register(identity)
        return identity

    def register(self, identity: ScopedIdentity) -> ScopedIdentity:
        existing = self._identities.get(identity.value)
        if existing is not None and existing != identity:
            raise IdentityConflictError(
                f"identity {identity.value} already has namespace/scope {existing}"
            )
        self._identities[identity.value] = identity
        return identity

    def resolve(
        self,
        value: UUID | str,
        *,
        namespace: IdentityNamespace | None = None,
        household_id: UUID | None = None,
    ) -> ScopedIdentity:
        parsed = value if isinstance(value, UUID) else UUID(value)
        try:
            identity = self._identities[parsed]
        except KeyError as error:
            raise UnknownIdentityError(str(parsed)) from error
        if namespace is not None and identity.namespace != namespace:
            raise IdentityConflictError(
                f"identity {parsed} is {identity.namespace.value}, not {namespace.value}"
            )
        if household_id is not None and identity.household_id != household_id:
            raise IdentityConflictError(
                f"identity {parsed} does not belong to household {household_id}"
            )
        return identity

    def contains(self, value: UUID) -> bool:
        return value in self._identities
