"""Read-only pull of the Lite User Collection Report from the Django admin.

Usage: python tools/fetch_lite_mv.py <__Host-sessionid cookie> [out.csv] [max_pages]
Log out of the admin afterwards; the cookie is a live session.
"""
import csv, html, sys, time, urllib.parse, urllib.request
from html.parser import HTMLParser

BASE = ("https://esgintelligence.gamuda.com.my/admin/reports/"
        "liteusercollectionreportmv/")
COOKIE = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else "/Users/ridhamohamed/Downloads/lite_user_collection_report.csv"
MAX_PAGES = int(sys.argv[3]) if len(sys.argv) > 3 else 1


def get(page: int) -> str:
    url = BASE + ("?" + urllib.parse.urlencode({"p": page}) if page > 1 else "")
    req = urllib.request.Request(url, headers={
        "Cookie": f"__Host-sessionid={COOKIE}",
        "User-Agent": "Mozilla/5.0 (mini-reid one-off export)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


class Table(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = self.in_cell = self.in_head = False
        self.headers, self.rows, self.row = [], [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table" and a.get("id") == "result_list":
            self.in_table = True
        elif self.in_table and tag == "thead":
            self.in_head = True
        elif self.in_table and tag == "tr":
            self.row = []
        elif self.in_table and tag in ("th", "td"):
            self.in_cell = True
            self.row.append("") if self.row is not None else None

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = self.in_head = False
        elif tag == "thead":
            self.in_head = False
        elif tag == "tr" and self.row is not None:
            if self.in_head:
                self.headers = self.row
            elif any(c.strip() for c in self.row):
                self.rows.append(self.row)
            self.row = None
        elif tag in ("th", "td"):
            self.in_cell = False

    def handle_data(self, data):
        if self.in_cell and self.row:
            self.row[-1] += data


def text(markup: str, needle: str) -> str:
    i = markup.find(needle)
    return markup[i:i + 120] if i >= 0 else ""


def main():
    all_rows, headers = [], []
    page = 1
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        while page <= MAX_PAGES:
            body = get(page)
            if page == 1:
                if "Log out" not in body and "Log in" in body:
                    print("NOT LOGGED IN — session cookie rejected/expired")
                    return 2
                print("title:", html.unescape(text(body, "<title>"))[:100])
                import re
                m = re.search(r"([\d,]+)\s+lite user collection reports?", body, re.I)
                print("count line:", m.group(0) if m else "not found")
            t = Table()
            t.feed(body)
            if page == 1:
                headers = [h.strip() for h in t.headers]
                print("columns:", headers)
            for r in t.rows:
                w.writerow([c.strip() for c in r][:len(headers)] if headers else r)
            all_rows.extend(t.rows)
            print(f"page {page}: {len(t.rows)} rows (total {len(all_rows)})")
            if len(t.rows) < 100:
                break
            page += 1
            time.sleep(0.4)
    print("wrote", OUT, "rows", len(all_rows))


if __name__ == "__main__":
    sys.exit(main())
