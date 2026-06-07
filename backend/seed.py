import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed local knowledge snippets through the backend API.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--file", default=str(Path(__file__).with_name("seed_knowledge.json")), help="Seed JSON file")
    args = parser.parse_args()

    seed_path = Path(args.file)
    items = json.loads(seed_path.read_text(encoding="utf-8"))
    payload = json.dumps({"items": items}).encode("utf-8")
    url = f"{args.base_url.rstrip('/')}/api/knowledge/seed"
    request = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
    print(f"Seeded {body.get('inserted_count', 0)} knowledge snippets from {seed_path}")


if __name__ == "__main__":
    main()
