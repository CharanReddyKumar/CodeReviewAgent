import sys
from pathlib import Path

from best_practices_docs import ingest_best_practices_docs


def main():
    if len(sys.argv) < 3:
        print("Usage: python index_best_practices_docs.py <folder> <source_name>")
        sys.exit(1)

    folder = Path(sys.argv[1])
    source = sys.argv[2]
    ingest_best_practices_docs(folder, source)


if __name__ == "__main__":
    main()
