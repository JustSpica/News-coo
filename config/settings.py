import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]
FEEDS_PATH: Path = Path(__file__).parent / "feeds.yaml"
