"""Run offline tests with fresh data/config roots; never load the developer .env."""
import os
from pathlib import Path
import socket
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix="texa-audit-tests-") as directory:
        root = Path(directory)
        for key in list(os.environ):
            if any(word in key for word in ("API_KEY", "API_TOKEN", "API_BASE", "PROXY")):
                os.environ.pop(key, None)
        for key, name in {
            "DATA_DIR": "data", "PROGRESS_PATH": "data/progress",
            "VECTOR_DB_PATH": "data/vector_db", "BOOKS_PATH": "data/books",
            "CHAPTERS_PATH": "data/chapters", "IMAGES_PATH": "data/images",
            "MINERU_OUTPUT_PATH": "mineru", "BACKUP_PATH": "backups",
            "LLM_PROFILE_PATH": "profiles.json", "ENV_PATH": "empty.env",
        }.items():
            os.environ[key] = str(root / name)
        (root / "empty.env").touch()
        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", ANONYMIZED_TELEMETRY="False")
        connect = socket.socket.connect

        def local_connect(sock, address):
            if isinstance(address, tuple) and address[0] not in ("localhost", "127.0.0.1", "::1"):
                raise OSError("audit harness prohibits external network connections")
            return connect(sock, address)

        socket.socket.connect = local_connect
        import pytest
        return pytest.main(sys.argv[1:] or ["-q"])


if __name__ == "__main__":
    raise SystemExit(main())
