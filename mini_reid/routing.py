"""Route a triager ticket to the account owners.

Chain: requester email -> (MV anchor for SME users | child company parent)
-> programme (GHB / GVC / SAFE) -> hub client members. Accounts with no hub
client fall back to the programme owners.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
EXPORTS = HOME / "Downloads"
HUB_CONFIG = HOME / "Downloads/IOI Stock Takes/stocktake-hub/config/config-live.json"
OUT = "routing.json"
ALIASES = "routing_aliases.json"
MAX_AGE_HOURS = 24

# Per Ridha, 2026-11-09: SAFE is his alone; GHB and GVC are the three of them.
PROGRAMME_OWNERS = {
    "GHB": ["ridha@pantas.com", "akasha@pantas.com", "azleena@pantas.com"],
    "GVC": ["ridha@pantas.com", "akasha@pantas.com", "azleena@pantas.com"],
    "SAFE": ["ridha@pantas.com"],
    "ENT": ["ridha@pantas.com"],
}
GHB_ANCHORS = {
    "exim bank", "exim bank (ghb)", "exim bank (gegi programme)",
    "sme bank (ghb)", "agrobank (ghb)", "bank rakyat (ghb)",
    "maybank islamic (ghb)", "hong leong islamic bank (ghb)",
}
SAFE_ANCHOR = "dti-spark (anchor)"

# Enterprise accounts: exactly who Ridha wants tagged (2026-11-09). Every
# other enterprise account tags Ridha alone.
ACCOUNT_OWNERS = {
    "gamuda bhd": ["ridha@pantas.com"],
    "ioi properties group": ["xieyi@pantas.com", "ridha@pantas.com"],
    "sime darby property berhad": ["kyewen@pantas.com"],
    "s p setia bhd": ["charanya@pantas.com"],
    "permodalan nasional berhad (pnb)": ["akasha@pantas.com", "raj@pantas.com"],
    "berjaya group": ["xieyi@pantas.com"],
    "edotco group sdn bhd": ["raj@pantas.com", "charanya@pantas.com"],
    "mbm resources bhd": ["azleena@pantas.com"],
    "kelington group berhad": ["kyewen@pantas.com", "ridha@pantas.com"],
    "bintulu port holdings berhad": ["azleena@pantas.com"],
    "eupe corporation berhad": ["ridha@pantas.com", "charanya@pantas.com"],
    "tmk chemical bhd": ["azleena@pantas.com", "raj@pantas.com"],
    "pkt logistics group sdn bhd": ["raj@pantas.com", "azleena@pantas.com"],
    "knight frank malaysia": ["ridha@pantas.com", "charanya@pantas.com"],
    "allianz malaysia berhad": ["charanya@pantas.com", "azleena@pantas.com"],
}


def account_owners(anchor: str) -> list[str] | None:
    key = _norm(anchor)
    if key in ACCOUNT_OWNERS:
        return list(ACCOUNT_OWNERS[key])
    for name, owners in ACCOUNT_OWNERS.items():
        if len(name) >= 5 and (name in key or key in name):
            return list(owners)
    return None


# Anchor names the config's client names do not match on their own.
CLIENT_OVERRIDES = {
    "mbm resources bhd": ["mbmr"],
    "ambank holdings berhad": ["ambank-ee", "ambank-fe"],
    "berjaya group": ["berjaya-property-berhad"],
    "permodalan nasional berhad (pnb)": ["pnb-enterprise"],
}

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
TICKET = re.compile(r"\b([A-Z][A-Z0-9]{0,9}-\d+)\b")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ()-]+", " ", (text or "").lower())).strip()


def programme(anchor: str, lite_anchors: set[str] | None = None) -> str:
    """GHB / GVC / SAFE are Pantas Lite programmes; everything else is ENT."""
    key = _norm(anchor)
    if key in GHB_ANCHORS:
        return "GHB"
    if key == SAFE_ANCHOR:
        return "SAFE"
    if lite_anchors is None or key in lite_anchors:
        return "GVC"
    return "ENT"


def flatten_message(message: dict) -> str:
    """Demo App now posts Block Kit cards; the text is only "New ticket: X".
    Flatten the blocks so Requester/Company/Description can be parsed."""
    parts: list[str] = [message.get("text") or ""]

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("type") == "plain_text" and isinstance(node.get("text"), str):
                parts.append(node["text"])
            elif node.get("type") == "mrkdwn" and isinstance(node.get("text"), str):
                parts.append(node["text"])
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(message.get("blocks") or [])
    walk(message.get("attachments") or [])
    return "\n".join(p for p in parts if p)


def _field(text: str, name: str) -> str:
    m = re.search(rf"\*{name}:\*\s*\n?\s*([^\n*]+)", text or "")
    return (m.group(1) if m else "").strip()[:120]


def parse_card(text: str) -> dict:
    """Pull the fields a triager card carries: key, email, title, company."""
    text = text or ""
    email = next((m.group(0).lower() for m in EMAIL.finditer(text)
                  if "pantas.com" not in m.group(0).lower()), "")
    key = ""
    title = ""
    for tick in TICKET.finditer(text):
        tail = text[tick.end():].lstrip(" :")
        found = re.split(r"\*Requester|\n| \| ", tail, maxsplit=1)[0]
        found = re.sub(r"[*_`]+", "", found).strip()[:120]
        if found:                 # "New ticket: PHD-x" has no title; the
            key, title = tick.group(1), found   # block header does
            break
        key = key or tick.group(1)
    company = _field(text, "Company")
    organisation = _field(text, "Organization")
    if company.lower() in {"unmapped", ""}:
        company = ""
    if organisation.lower() == "unmapped":
        organisation = ""
    return {"email": email, "key": key, "title": title,
            "company": company, "organisation": organisation}


GENERIC_COMPANIES = {"pantas", "all project", "xxx", "test", "demo",
                     "pantas test company", "parent company placeholder"}


def lookup_company(companies: dict[str, dict], name: str) -> dict | None:
    """Company/organisation name -> account. Exact first, then conservative
    containment; single generic words ("Pantas", "Test") never match."""
    key = _norm(name)
    if not key or key in GENERIC_COMPANIES:
        return None
    if key in companies:
        return companies[key]
    words = set(key.split())
    best: tuple[int, dict] | None = None
    for candidate, route in companies.items():
        if candidate in GENERIC_COMPANIES:
            continue
        tokens = set(candidate.split())
        hit = ((len(candidate) >= 8 and candidate in key)
               or (len(key) >= 8 and key in candidate)
               or (len(tokens) >= 2 and tokens <= words))
        if hit and (best is None or len(candidate) > best[0]):
            best = (len(candidate), route)
    return best[1] if best else None


def client_members(hub: dict) -> dict[str, list[str]]:
    return {slug: list(cfg.get("members") or [])
            for slug, cfg in (hub.get("clients") or hub).items()}


def anchor_clients(hub: dict) -> dict[str, list[str]]:
    """Normalised anchor name -> hub client slugs."""
    out: dict[str, list[str]] = {}
    for slug, cfg in (hub.get("clients") or hub).items():
        if slug in {"ghb", "gvc", "safe"}:   # programme buckets, not accounts
            continue
        names = {_norm(cfg.get("name") or ""), _norm(slug)}
        for name in names:
            if name:
                out.setdefault(name, []).append(slug)
    return out


def match_clients(anchor: str, by_name: dict[str, list[str]]) -> list[str]:
    key = _norm(anchor)
    if key in CLIENT_OVERRIDES:
        return CLIENT_OVERRIDES[key]
    if key in by_name:
        return by_name[key]
    words = set(key.split())
    for name, slugs in by_name.items():
        if len(name) >= 5 and (name in key or key in name):
            return slugs
        # Short client names ("TMK", "DXN", "IOI") match as whole words.
        if len(name) >= 3 and set(name.split()) <= words:
            return slugs
    return []


def load_hub(path: Path = HUB_CONFIG) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _rows(path: Path) -> list[dict]:
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _latest(pattern: str) -> Path:
    """Newest dated export (ChildCompany-YYYY-MM-DD.csv) in ~/Downloads."""
    found = sorted(EXPORTS.glob(pattern))
    return found[-1] if found else EXPORTS / pattern.replace("*", "")


def build(routing_path: str | Path = OUT) -> dict:
    hub = load_hub()
    members = client_members(hub)
    by_name = anchor_clients(hub)

    anchors = {}
    sme_names: dict[str, str] = {}
    for row in _rows(EXPORTS / "lite_user_collection_report.csv"):
        email = (row.get("User email") or "").strip().lower()
        anchor = (row.get("Anchor") or "").strip()
        sme = (row.get("Sme name") or "").strip()
        if email and anchor:
            anchors[email] = anchor
        if sme and anchor:
            sme_names[_norm(sme)] = anchor

    children = {}
    for row in _rows(_latest("ChildCompany-*.csv")):
        children[(row.get("name") or "").strip()] = (row.get("parent_company") or "").strip()
    parents: dict[str, str] = {}
    for row in _rows(_latest("ChildCompanyUser-*.csv")):
        email = (row.get("user") or "").strip().lower()
        parent = children.get((row.get("child_company") or "").strip(), "")
        if email and email not in parents:
            parents[email] = parent

    # Anchors seen in the Lite MV are the Lite (GVC) accounts; the rest of the
    # platform is enterprise.
    lite_anchors = {_norm(a) for a in set(anchors.values()) if a}

    def route_for(anchor: str) -> dict:
        prog = programme(anchor, lite_anchors)
        if prog == "ENT":
            owners = account_owners(anchor) or ["ridha@pantas.com"]
        else:
            owners = []
            for slug in match_clients(anchor, by_name):
                owners.extend(members.get(slug) or [])
            owners = list(dict.fromkeys(owners)) or list(PROGRAMME_OWNERS[prog])
        return {"anchor": anchor, "programme": prog, "owners": owners}

    emails: dict[str, dict] = {}
    for email in set(anchors) | set(parents):
        anchor = anchors.get(email) or parents.get(email) or ""
        if anchor:
            emails[email] = route_for(anchor)

    # Company-name fallback for cards that carry no requester email: the Lite
    # MV names the SME company; the child-company export names the rest.
    companies: dict[str, dict] = {}
    for sme, anchor in sme_names.items():
        companies.setdefault(sme, route_for(anchor))
    for name, parent in children.items():
        if name and parent and parent != "SME parent company":
            companies.setdefault(_norm(name), route_for(parent))
    for parent in set(children.values()):
        if parent and parent != "SME parent company":
            companies.setdefault(_norm(parent), route_for(parent))
    # Learned aliases: "alias: <company> = <account>" in chat.
    try:
        learned = json.loads(Path(ALIASES).read_text())
    except (OSError, ValueError):
        learned = {}
    for company, route in learned.items():
        if isinstance(route, dict) and route.get("owners"):
            companies[company] = route

    # Domain fallback: a requester who is not a platform user but works at a
    # known client (bazil@my.knightfrank.com) still routes to that account.
    domains: dict[str, dict] = {}
    try:
        clients = json.loads(Path("clients.json").read_text())
    except (OSError, ValueError):
        clients = {}
    for slug, cfg in clients.items():
        prog = {"ghb": "GHB", "gvc": "GVC", "safe": "SAFE"}.get(slug, "ENT")
        owners = list(members.get(slug) or []) or list(PROGRAMME_OWNERS[prog])
        if prog == "ENT":
            owners = account_owners(cfg.get("name") or slug) or ["ridha@pantas.com"]
        for domain in cfg.get("domains") or []:
            key = domain.lower()
            entry = domains.setdefault(key, {"anchor": cfg.get("name") or slug,
                                             "programme": prog, "owners": []})
            entry["owners"] = list(dict.fromkeys(entry["owners"] + owners))
    data = {"version": 5,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "emails": emails, "domains": domains, "companies": companies}
    Path(routing_path).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    return data


def ensure_fresh(routing_path: str | Path = OUT) -> dict:
    """Rebuild when the cache is missing, stale, or older than the exports."""
    path = Path(routing_path)
    stale = True
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if data.get("version") != 5:
                raise ValueError("old routing cache")
            built = datetime.fromisoformat(data.get("built_at") or "")
            newest_export = max(
                (p.stat().st_mtime for p in (EXPORTS / "lite_user_collection_report.csv",
                                             _latest("ChildCompany-*.csv"),
                                             _latest("ChildCompanyUser-*.csv"))
                 if p.exists()), default=0)
            stale = ((datetime.now(timezone.utc) - built).total_seconds() > MAX_AGE_HOURS * 3600
                     or built.timestamp() < newest_export)
            if not stale:
                return data
        except (OSError, ValueError):
            pass
    return build(path)


def owner_ids(owners: list[str], directory_path: str = "directory.json") -> list[str]:
    """Hub emails -> Slack ids, via the cached directory."""
    try:
        directory = json.loads(Path(directory_path).read_text())
    except (OSError, ValueError):
        return []
    by_email = {(rec or {}).get("email", "").lower(): uid
                for uid, rec in directory.items() if (rec or {}).get("email")}
    return [by_email[e] for e in owners if e in by_email]


FALLBACK_WINDOW = 10      # look at the last N tickets
FALLBACK_RATIO = 0.20     # alert when this share fell back
EXPORT_MAX_AGE_DAYS = 7   # ask for a fresh Django admin export


def exports_age_days() -> float:
    """Age of the newest dated child-company export."""
    newest = _latest("ChildCompany-*.csv")
    try:
        return (datetime.now().timestamp() - newest.stat().st_mtime) / 86400
    except OSError:
        return 999.0


def needs_alert(total: int, fallback: int) -> bool:
    """Too many tickets in the window fell back to the default owner."""
    return total >= FALLBACK_WINDOW and fallback / total >= FALLBACK_RATIO


def add_alias(company: str, target: str) -> dict:
    """Teach a company-name alias ("Horizon Hills = Gamuda") and rebuild."""
    key = _norm(company)
    if not key:
        raise ValueError("company name required")
    data = ensure_fresh()
    route = None
    wanted = _norm(target)
    for candidate in data.get("companies", {}).values():
        anchor = _norm(candidate.get("anchor") or "")
        if anchor == wanted or (len(wanted) >= 4
                                and (wanted in anchor or anchor in wanted)):
            route = candidate
            break
    if route is None:
        route = {"anchor": target.strip(),
                 "programme": "ENT",
                 "owners": account_owners(target) or ["ridha@pantas.com"]}
    path = Path(ALIASES)
    try:
        aliases = json.loads(path.read_text())
    except (OSError, ValueError):
        aliases = {}
    aliases[key] = route
    path.write_text(json.dumps(aliases, indent=1, ensure_ascii=False) + "\n")
    Path(OUT).unlink(missing_ok=True)   # rebuild with the alias next time
    return route
