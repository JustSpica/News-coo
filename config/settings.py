import os
from pathlib import Path

from dotenv import load_dotenv

FEEDS_PATH: Path = Path(__file__).parent / "feeds.yaml"


def get_discord_token() -> str:
    load_dotenv()
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        msg = "DISCORD_TOKEN must be set in the environment or .env file"
        raise RuntimeError(msg)
    return token
