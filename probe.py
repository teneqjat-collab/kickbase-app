"""Erkundungslauf für die inoffizielle Kickbase-API (v4).

Loggt sich ein, findet die Liga, ruft die wichtigsten Endpunkte ab und speichert
die Antworten in ./out. Das Passwort und der Token werden nie ausgegeben.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "https://api.kickbase.com"
EMAIL = os.environ["KICKBASE_EMAIL"]
PASSWORD = os.environ["KICKBASE_PASSWORD"]
LEAGUE_NAME = os.environ.get("KICKBASE_LEAGUE", "POWER RANGERS").lower()
LEAGUE_ID = os.environ.get("KICKBASE_LEAGUE_ID", "")

OUT = "out"
os.makedirs(OUT, exist_ok=True)
token = None
status_lines = []


def call(method, path, body=None, auth=True):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    }
    if auth and token:
        # Je nach API-Stand wird der Token als Cookie oder als Header erwartet.
        headers["Cookie"] = f"kkstrauth={token}"
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    except Exception as e:  # Netzwerkfehler o. Ä.
        return 0, f"Fehler: {e}"
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw[:500]


def walk(o):
    """Liefert alle Dicts in einer verschachtelten Struktur."""
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def skel(o, d=0):
    if d > 5:
        return "..."
    if isinstance(o, dict):
        return {k: skel(v, d + 1) for k, v in list(o.items())[:40]}
    if isinstance(o, list):
        return [f"len={len(o)}"] + ([skel(o[0], d + 1)] if o else [])
    if isinstance(o, str):
        return "str:" + o[:24]
    return f"{type(o).__name__}:{o}"


shapes = {}


def save(name, status, data):
    with open(f"{OUT}/{name}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    shapes[name] = {"status": status, "shape": skel(data)}
    status_lines.append(f"{status}  {name}")
    print(f"{status}  {name}")


def finish(code=0):
    with open(f"{OUT}/shape.txt", "w", encoding="utf-8") as f:
        json.dump(shapes, f, ensure_ascii=False, indent=1)
    with open(f"{OUT}/status.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(status_lines))
    sys.exit(code)


# 1) Login --------------------------------------------------------------
status, resp = call(
    "POST",
    "/v4/user/login",
    {"em": EMAIL, "pass": PASSWORD, "loy": False, "rep": {}},
    auth=False,
)
print("Login:", status)
if status != 200 or not isinstance(resp, dict):
    print("Login fehlgeschlagen. Antwort (gekürzt):", str(resp)[:300])
    finish(1)
for d in walk(resp):
    if "tkn" in d:
        token = d["tkn"]
        break
if not token:
    print("Kein Token gefunden. Felder der Antwort:", list(resp.keys()))
    finish(1)
# Nur die Struktur speichern, keine persönlichen Werte oder Token
shapes["login"] = {"status": status, "shape": {k: type(v).__name__ for k, v in resp.items()}}

# 2) Liga finden --------------------------------------------------------
league_id = LEAGUE_ID
for path in ("/v4/leagues/selection", "/v4/leagues"):
    status, data = call("GET", path)
    save("leagues_" + path.rsplit("/", 1)[-1], status, data)
    if league_id or status != 200:
        continue
    for d in walk(data):
        names = [v for v in d.values() if isinstance(v, str) and LEAGUE_NAME in v.lower()]
        ids = [d[k] for k in ("i", "id", "lid", "leagueId") if k in d]
        if names and ids:
            league_id = str(ids[0])
            break
if not league_id:
    print("Liga nicht gefunden. Siehe out/shape.txt.")
    finish(1)
print("Liga-ID gefunden.")

# 3) Liga-Endpunkte -----------------------------------------------------
manager_ids = []
for name in ("ranking", "market", "squad", "activitiesFeed", "me", "me/budget", "overview", "settings"):
    status, data = call("GET", f"/v4/leagues/{league_id}/{name}")
    save(name.replace("/", "_"), status, data)
    if name == "ranking" and status == 200:
        for d in walk(data):
            has_id = [k for k in ("i", "id", "userId") if k in d]
            has_name = [k for k in ("n", "name", "unm", "userName") if k in d]
            if has_id and has_name and str(d[has_id[0]]) not in manager_ids:
                manager_ids.append(str(d[has_id[0]]))

# 4) Daten anderer Manager ----------------------------------------------
if manager_ids:
    m = manager_ids[0]
    for name in ("squad", "transfer"):
        status, data = call("GET", f"/v4/leagues/{league_id}/managers/{m}/{name}")
        save("manager_" + name, status, data)
else:
    print("Keine Manager-IDs im Ranking erkannt.")

finish(0)
