import json
from pathlib import Path

class ProposalStore:
    def __init__(self, path="data/proposals.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, proposal):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(proposal, ensure_ascii=False) + "\n")
