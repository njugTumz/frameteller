"""Domain errors. Each one names a broken story rule."""


class DomainError(Exception):
    """Base class for every rule violation in the domain."""


class UnknownCharacterError(DomainError):
    """A shot references a character that is not in the bible."""


class CastNotApprovedError(DomainError):
    """Panels cannot be drawn before the user approves the cast (ADR 0004)."""


class MissingReferenceError(DomainError):
    """The cast cannot be approved while a character has no reference sheet."""


class ShotOrderError(DomainError):
    """Shot numbers must run 1..n without gaps, and reorders must be permutations."""


class RevisionOrderError(DomainError):
    """Panel revisions only ever increase."""


class UnknownShotError(DomainError):
    """The shot does not exist in this project."""


class PanelNotReadyError(DomainError):
    """The operation needs a rendered panel."""


class UnknownObjectError(DomainError):
    """No cached mask with that id on the panel's current revision."""


class InvalidValueError(DomainError):
    """A value object was built with impossible values (negative time, empty box...)."""
