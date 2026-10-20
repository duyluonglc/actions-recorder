"""Fill in the project's GitHub owner and donation accounts everywhere.

    python tools/set_links.py --owner myname --paypal myname [--amounts 5,10] [--sponsors]

Re-running is safe: the previous values are remembered in tools/links.json.
"""
import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["README.md", "README.vi.md", "docs/INSTALL.md", "docs/INSTALL.vi.md", "docs/FIRST-LAUNCH-macOS.txt",
         "docs/FIRST-LAUNCH-Windows.txt", ".github/release-notes.md", "macrorecorder/links.py"]
STATE = os.path.join(ROOT, "tools", "links.json")


def badges(owner: str, paypal: str, sponsors: bool, amounts: list[int]) -> str:
    out = []
    if paypal:
        for amt in amounts:
            out.append(f"[![Donate ${amt}](https://img.shields.io/badge/Donate-%24{amt}-00457C?logo=paypal&logoColor=white)]"
                       f"(https://paypal.me/{paypal}/{amt}USD)")
        out.append(f"[![PayPal](https://img.shields.io/badge/PayPal-any%20amount-00457C?logo=paypal&logoColor=white)]"
                   f"(https://paypal.me/{paypal})")
    if sponsors:
        out.append(f"[![GitHub Sponsors](https://img.shields.io/badge/GitHub%20Sponsors-Sponsor-EA4AAA"
                   f"?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/{owner})")
    return " ".join(out) if out else "_(donation links coming soon)_"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True, help="GitHub user or organisation")
    ap.add_argument("--repo", default="actions-recorder")
    ap.add_argument("--paypal", default="", help="paypal.me name")
    ap.add_argument("--amounts", default="5,10", help="quick PayPal amounts in USD, e.g. 5,10")
    ap.add_argument("--sponsors", action="store_true", help="GitHub Sponsors is enabled for --owner")
    a = ap.parse_args()

    prev = json.load(open(STATE)) if os.path.exists(STATE) else {}
    old_owner = prev.get("owner", "OWNER")
    old_repo = prev.get("repo", "actions-recorder")
    old_badges = prev.get("badges", "DONATE_LINKS")
    amounts = [int(x) for x in a.amounts.split(",") if x.strip()]
    new_badges = badges(a.owner, a.paypal, a.sponsors, amounts)
    for rel in FILES:
        p = os.path.join(ROOT, rel)
        s = open(p, encoding="utf-8").read()
        s = s.replace(f"github.com/{old_owner}/{old_repo}", f"github.com/{a.owner}/{a.repo}")
        s = s.replace(old_badges, new_badges)
        if rel.endswith("links.py"):
            s = re.sub(r'GITHUB_OWNER = ".*?"', f'GITHUB_OWNER = "{a.owner}"', s)
            s = re.sub(r'GITHUB_REPO = ".*?"', f'GITHUB_REPO = "{a.repo}"', s)
            s = re.sub(r'PAYPAL_ME = ".*?"', f'PAYPAL_ME = "{a.paypal}"', s)
            s = re.sub(r'DONATE_AMOUNTS = \(.*?\)', f'DONATE_AMOUNTS = ({", ".join(map(str, amounts))}{"," if len(amounts) == 1 else ""})', s)
            s = re.sub(r'GITHUB_SPONSORS = \w+', f'GITHUB_SPONSORS = {a.sponsors}', s)
        open(p, "w", encoding="utf-8").write(s)
    funding = []
    if a.sponsors:
        funding.append(f"github: [{a.owner}]")
    if a.paypal:
        funding.append(f"custom: [\"https://paypal.me/{a.paypal}\"]")
    os.makedirs(os.path.join(ROOT, ".github"), exist_ok=True)
    with open(os.path.join(ROOT, ".github", "FUNDING.yml"), "w") as f:
        f.write("\n".join(funding) + "\n")
    json.dump({"owner": a.owner, "repo": a.repo, "badges": new_badges}, open(STATE, "w"), indent=1)
    print("Links updated for", f"github.com/{a.owner}/{a.repo}")


if __name__ == "__main__":
    main()
