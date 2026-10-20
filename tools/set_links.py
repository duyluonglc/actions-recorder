"""Fill in the project's GitHub owner and donation accounts everywhere.

    python tools/set_links.py --owner myname --paypal myname --bmc myname [--sponsors]

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


def badges(owner: str, paypal: str, bmc: str, sponsors: bool) -> str:
    out = []
    if paypal:
        out.append(f"[![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?logo=paypal&logoColor=white)]"
                   f"(https://paypal.me/{paypal})")
    if bmc:
        out.append(f"[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support-FFDD00"
                   f"?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/{bmc})")
    if sponsors:
        out.append(f"[![GitHub Sponsors](https://img.shields.io/badge/GitHub%20Sponsors-Sponsor-EA4AAA"
                   f"?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/{owner})")
    return " ".join(out) if out else "_(donation links coming soon)_"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True, help="GitHub user or organisation")
    ap.add_argument("--repo", default="actions-recorder")
    ap.add_argument("--paypal", default="", help="paypal.me name")
    ap.add_argument("--bmc", default="", help="buymeacoffee.com name")
    ap.add_argument("--sponsors", action="store_true", help="GitHub Sponsors is enabled for --owner")
    a = ap.parse_args()

    prev = json.load(open(STATE)) if os.path.exists(STATE) else {}
    old_owner = prev.get("owner", "OWNER")
    old_repo = prev.get("repo", "actions-recorder")
    old_badges = prev.get("badges", "DONATE_LINKS")
    new_badges = badges(a.owner, a.paypal, a.bmc, a.sponsors)
    for rel in FILES:
        p = os.path.join(ROOT, rel)
        s = open(p, encoding="utf-8").read()
        s = s.replace(f"github.com/{old_owner}/{old_repo}", f"github.com/{a.owner}/{a.repo}")
        s = s.replace(old_badges, new_badges)
        if rel.endswith("links.py"):
            s = re.sub(r'GITHUB_OWNER = ".*?"', f'GITHUB_OWNER = "{a.owner}"', s)
            s = re.sub(r'GITHUB_REPO = ".*?"', f'GITHUB_REPO = "{a.repo}"', s)
            s = re.sub(r'\("PayPal", ".*?"\)', f'("PayPal", "{"https://paypal.me/" + a.paypal if a.paypal else ""}")', s)
            s = re.sub(r'\("Buy Me a Coffee", ".*?"\)',
                       f'("Buy Me a Coffee", "{"https://buymeacoffee.com/" + a.bmc if a.bmc else ""}")', s)
            s = re.sub(r'\("GitHub Sponsors", .*?\)',
                       '("GitHub Sponsors", f"https://github.com/sponsors/{GITHUB_OWNER}")' if a.sponsors
                       else '("GitHub Sponsors", "")', s)
        open(p, "w", encoding="utf-8").write(s)
    funding = []
    if a.sponsors:
        funding.append(f"github: [{a.owner}]")
    if a.bmc:
        funding.append(f"buy_me_a_coffee: {a.bmc}")
    if a.paypal:
        funding.append(f"custom: [\"https://paypal.me/{a.paypal}\"]")
    os.makedirs(os.path.join(ROOT, ".github"), exist_ok=True)
    with open(os.path.join(ROOT, ".github", "FUNDING.yml"), "w") as f:
        f.write("\n".join(funding) + "\n")
    json.dump({"owner": a.owner, "repo": a.repo, "badges": new_badges}, open(STATE, "w"), indent=1)
    print("Links updated for", f"github.com/{a.owner}/{a.repo}")


if __name__ == "__main__":
    main()
