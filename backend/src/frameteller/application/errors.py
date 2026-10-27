"""Application errors: things that stop a use case but are not story rules."""


class ApplicationError(Exception):
    """Base class for use-case failures."""

    user_message = "Something went wrong. Please try again."


class BudgetExceededError(ApplicationError):
    """The call would take spend past the per-project or per-day limit."""

    user_message = "This project has reached its spending limit for now."


class NothingToSegmentError(ApplicationError):
    """SAM found no object at the clicked point."""

    user_message = "Nothing to select there. Try clicking right on the object."


class ModelError(ApplicationError):
    """A model call failed. Adapters map provider failures to one of the subclasses."""

    def __init__(self, model: str, detail: str = "") -> None:
        super().__init__(f"{model}: {detail}" if detail else model)
        self.model = model


class ModelUnavailableError(ModelError):
    user_message = "The model is having trouble right now. We'll keep your work; try again in a minute."


class ModelRateLimitedError(ModelError):
    user_message = "Lots of requests right now. Give it a few seconds and try again."


class ModelTimeoutError(ModelError):
    user_message = "That took too long. Try again."


class ModelRejectedError(ModelError):
    """The provider refused the request (4xx other than 429). Retrying the same request will not help."""

    user_message = "The model couldn't do that one. Try rephrasing it."


class InvalidModelOutputError(ModelError):
    """The model answered, but not in the shape we asked for, even after one retry."""

    user_message = "The director got confused by that line. Try saying it again."
