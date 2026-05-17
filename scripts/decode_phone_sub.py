import base64
import sys

b64 = sys.stdin.read().strip()
raw = base64.b64decode(b64).decode("utf-8")
lines = raw.split("\n")
print("decoded_len", len(raw))
print("line_count", len(lines))
for i, line in enumerate(lines):
    if not line.strip():
        print(i, "(empty)")
        continue
    kind = "json" if line.lstrip().startswith("{") else "uri"
    print(i, kind, len(line), line[:60].replace("\n", " "))
