from __future__ import annotations

from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import CHROMA_COLLECTION_NAME, CHROMA_DB_DIR, EMBEDDING_MODEL
from app.rag.vector_db import ingest_guide_chunks_to_chroma, load_guide_chunks


def main() -> int:
    chunks = load_guide_chunks()
    print("=== 准备写入 Chroma ===")
    print(f"chunk_count: {len(chunks)}")
    print(f"embedding_model: {EMBEDDING_MODEL}")
    print(f"chroma_db_dir: {CHROMA_DB_DIR}")
    print(f"collection_name: {CHROMA_COLLECTION_NAME}")
    print()

    written_count = ingest_guide_chunks_to_chroma()

    print("=== 写入完成 ===")
    print(f"written_count: {written_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
