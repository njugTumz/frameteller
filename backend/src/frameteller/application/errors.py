"""Application errors: things that stop a use case but are not story rules."""


class ApplicationError(Exception):
    """Base class for use-case failures."""

    user_message = "Something went wrong. Please try again."


class BudgetExceededError(ApplicationError):
    """The call would take spend past the per-project or per-day limit."""

    user_message = "This project has reached its spending limit for now."


class StudioFullError(BudgetExceededError):
    """Today's spend across every project reached the global daily cap. Shared storyboards stay viewable."""

    user_message = "The studio is full for today. Come back tomorrow."


class LimitReachedError(ApplicationError):
    """A public-demo allowance is used up (per visitor or per project). The message says which and what next."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.user_message = message


class ScriptError(ApplicationError):
    """A script that cannot be told: empty, too long, or too many episodes or paragraphs. Says what to change."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.user_message = message


class RefusedUnchangedError(ApplicationError):
    """Try again on a sheet Muse Image refused, with the same description: it would be refused again (ADR 0019)."""

    user_message = "Muse Image turned this description down. Use the suggested description or edit it first."


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


class ModelContentFilteredError(ModelRejectedError):
    """The provider's safety filter refused the prompt (Muse Image: "content management policy")."""

    user_message = "Muse Image's safety filter turned this drawing down. Describe the character by look and role."


class InvalidModelOutputError(ModelError):
    """The model answered, but not in the shape we asked for, even after one retry."""

    user_message = "The director got confused by that line. Try saying it again."


class ProjectNotFoundError(ApplicationError):
    user_message = "We couldn't find that project."


class ShareNotFoundError(ApplicationError):
    user_message = "This link was turned off, or never existed."


class GalleryEntryNotFoundError(ApplicationError):
    user_message = "That storyboard isn't in the gallery."


class GallerySubmissionError(ApplicationError):
    """A submission that cannot go ahead: no consent, nothing drawn yet, or no recording to publish."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.user_message = message
