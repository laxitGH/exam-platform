from __future__ import annotations

from app.connections.mongo import init_mongo, close_mongo
from app.simulation import run_from_state


def main() -> None:
    init_mongo()
    try:
        run_from_state()
    finally:
        close_mongo()


if __name__ == "__main__":
    main()


