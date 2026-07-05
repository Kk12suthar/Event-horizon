from pathlib import Path
from dotenv import load_dotenv


def load_environment() -> None:
    """Load shared root env first, then legacy backend env if root is absent.

    Root `.env` is the intended common configuration for backend + agent-server.
    Existing `backend/.env` remains supported so local setups do not break while
    migrating secrets into the shared file.
    """
    backend_dir = Path(__file__).parent
    root_env = backend_dir.parent / ".env"
    backend_env = backend_dir / ".env"
    load_dotenv(root_env)
    load_dotenv(backend_env)
