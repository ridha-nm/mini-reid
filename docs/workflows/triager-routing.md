# Workflow: triager routing

Tag the account owner on a new Demo App ticket.

## Flow

1. Watcher reads `#bd-triager-agent` history from a stored baseline
   (`since_ts`) every cycle — search is not used (it misses cards that do
   not mention Ridha and lags).
2. The watermark (`since_ts`) survives sleep and restarts: after the Mac
   wakes, the next cycle replays the whole gap (paginated, 1,000 messages per
   cycle) and tags the tickets that arrived while it was off. Tickets that
   were also **Closed** inside that window are skipped.
3. **One trigger only**: the arrival card, `New ticket: PHD-xxxx` from
   **Demo App** (Block Kit — fields flattened before parsing). Nothing after
   it is ever tagged: acknowledgements, solution proposals, replies, SLA
   notices, rotation messages or closures. SLA notices, the
   weekly rotation, closed cards, `💬 … replied:` follow-ups and human
   chatter are ignored. One tag per ticket key, ever.
4. Reply goes in the card's thread:
   `*PHD-xxxx* — title` / `Requester · anchor (programme)` / `Owner: @tags`.
   The job stops there — no further replies on that ticket.
5. Routing chain (`routing.py`, rebuilt from `~/Downloads` exports when
   stale, cache `routing.json`):
   - requester **email** → Lite MV anchor (SME users) or child→parent
   - else email **domain** → `clients.json` domains
   - else card **Company**, then **Organization** → name match against MV
     SME names, child companies and parents (conservative; generic names
     like "Pantas" refused)
   - else Ridha.
6. Programme: GHB (all EXIM + `(GHB)` banks), SAFE (DTI-Spark) and GVC are
   **Pantas Lite**; everything else is **ENT** (enterprise).
7. Owners: ENT uses Ridha's explicit per-account list (`ACCOUNT_OWNERS` in
   `routing.py`), every other ENT account → Ridha. Lite accounts use their
   hub client's members, falling back to programme owners (GHB/GVC →
   Ridha+Akasha+Azleena, SAFE → Ridha).

## Sources

- Lite MV: `~/Downloads/lite_user_collection_report.csv` (scraped from the
  Django admin, Anchor column)
- `ChildCompany-*.csv`, `ChildCompanyUser-*.csv` (newest dated export)
- Hub roster: `~/Downloads/IOI Stock Takes/stocktake-hub/config/config-live.json`
- Domains: `clients.json`

## Learning and health

- `alias: <company> = <account>` (chat) saves a company-name mapping to
  `routing_aliases.json`; the next `routing.json` build uses it, so aliases
  survive export refreshes.
- Routing health is tracked in `triager_routed.json` (`stats`). Ridha gets a
  DM at most once a day when ≥10 recent tickets include ≥20% fallbacks, or
  when the exports are more than 7 days old — the DM lists unmapped
  companies and asks for fresh exports.

## State / code / tests

- State: `routing.json`, `triager_routed.json`
- Code: `routing.py`, `watcher.route_triager`
- Tests: `test_routing.py`
