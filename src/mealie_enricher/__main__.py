import uvicorn

from .app import create_app
from .config import load_settings
from .logging import configure_logging


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",
        port=int(settings.port),
        workers=1,
        log_config=None,
    )


if __name__ == "__main__":
    main()
