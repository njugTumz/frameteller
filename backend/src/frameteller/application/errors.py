"""Application errors: things that stop a use case but are not story rules."""


class ApplicationError(Exception):
    """Base class for use-case failures."""


class BudgetExceededError(ApplicationError):
    """The call would take spend past the per-project or per-day limit."""


class NothingToSegmentError(ApplicationError):
    """SAM found no object at the clicked point."""
