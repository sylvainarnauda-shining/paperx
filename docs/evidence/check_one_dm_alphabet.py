"""Static compatibility probe; downloads source as data, never imports/runs it.

Run from any directory: python3 docs/evidence/check_one_dm_alphabet.py
No model, image, client text or credentials are transmitted.
"""
import ast
import base64
import hashlib
import json
from urllib.request import Request, urlopen


BLOB = "6ccae081d4694fbdf77b5dbc03f4b9579132852e"
URL = f"https://api.github.com/repos/dailenson/One-DM/git/blobs/{BLOB}"
CASES = [
    "minimum elle ballon",
    "À Montpellier, Zoé étudie déjà ; où est le cahier ?",
    "L’élève écrit : cœur, Noël, façade, août.",
]


def main():
    request = Request(URL, headers={"User-Agent": "Paperx-static-compatibility-probe"})
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)
    source = base64.b64decode(payload["content"])
    digest = hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest()
    if digest != BLOB:
        raise ValueError("Upstream blob integrity mismatch")
    tree = ast.parse(source.decode("utf-8"))
    alphabet = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "letters" for target in node.targets)
    )
    if not isinstance(alphabet, str):
        raise TypeError("Expected a literal string alphabet")
    result = {
        "source": "https://github.com/dailenson/One-DM/blob/main/data_loader/loader.py",
        "blob_sha": BLOB,
        "method": "static AST inspection, no model execution",
        "cases": [{"text": text, "unsupported": sorted(set(text) - set(alphabet))} for text in CASES],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
