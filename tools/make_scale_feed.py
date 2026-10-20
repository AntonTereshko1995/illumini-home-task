"""Make a large feed for the scale requirement: N rows built from data/jobs_raw.jsonl.

    python tools/make_scale_feed.py --rows 200000 --out data/scale_feed.jsonl

Each row is an existing row with a new job_id and source_url, so the shapes match the real feed and most
location strings repeat (as they do in production).
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def main() -> None:
    """Write --rows rows to --out."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=200_000)
    parser.add_argument("--out", type=Path, default=Path("data/scale_feed.jsonl"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "jobs_raw.jsonl")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    source = [line for line in args.source.read_text(encoding="utf-8").splitlines() if line.strip()]
    with args.out.open("w", encoding="utf-8", newline="\n") as f:
        for i in range(args.rows):
            line = rng.choice(source)
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                f.write(line + "\n")
                continue
            row["job_id"] = f"S{i:07d}"
            row["source_url"] = f"https://feed.example/jobs/s{i:07d}"
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{args.rows} rows -> {args.out}")


if __name__ == "__main__":
    main()
