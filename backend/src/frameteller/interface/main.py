"""ASGI entry point: uvicorn frameteller.interface.main:app

Settings are validated at import, so a missing MODEL_API_KEY stops the process with a clear message.
"""

from frameteller.infrastructure.config import load_settings
from frameteller.infrastructure.observability import configure_logging
from frameteller.interface.app import create_app

settings = load_settings()
configure_logging(settings.log_level)
app = create_app(settings)
