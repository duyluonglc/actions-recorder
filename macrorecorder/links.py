"""Project links shown in the app (About, Support, Help). Updated by tools/set_links.py."""

GITHUB_OWNER = "duyluonglc"
GITHUB_REPO = "actions-recorder"
PAYPAL_ME = "luongnd"              # paypal.me/<name>; empty = hidden
DONATE_AMOUNTS = (5, 10)           # quick PayPal buttons, in USD
GITHUB_SPONSORS = True             # show the GitHub Sponsors button

REPO_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
RELEASES_URL = f"{REPO_URL}/releases/latest"
ISSUES_URL = f"{REPO_URL}/issues"
INSTALL_GUIDE_URL = f"{REPO_URL}/blob/main/docs/INSTALL.md"
INSTALL_GUIDE_VI_URL = f"{REPO_URL}/blob/main/docs/INSTALL.vi.md"
USER_GUIDE_URL = f"{REPO_URL}#readme"


def paypal_url(amount: int | None = None) -> str:
    """paypal.me link, optionally with the amount already filled in."""
    if not PAYPAL_ME:
        return ""
    return f"https://paypal.me/{PAYPAL_ME}" + (f"/{amount}USD" if amount else "")


def sponsors_url() -> str:
    return f"https://github.com/sponsors/{GITHUB_OWNER}" if GITHUB_SPONSORS else ""


def donate_options() -> list[tuple[str, str, str]]:
    """(kind, label, url) for the Support dialog: quick amounts first, then the open ones."""
    out = []
    if PAYPAL_ME:
        for a in DONATE_AMOUNTS:
            out.append(("amount", f"${a}", paypal_url(a)))
        out.append(("paypal", "PayPal", paypal_url()))
    if GITHUB_SPONSORS:
        out.append(("sponsors", "GitHub Sponsors", sponsors_url()))
    return out


def donate_links() -> list[tuple[str, str]]:
    return [(label, url) for kind, label, url in donate_options() if kind != "amount"]
