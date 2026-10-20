"""Project links shown in the app (About, Support, Help). Edit here only."""

GITHUB_OWNER = "OWNER"
GITHUB_REPO = "actions-recorder"

REPO_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
RELEASES_URL = f"{REPO_URL}/releases/latest"
ISSUES_URL = f"{REPO_URL}/issues"
INSTALL_GUIDE_URL = f"{REPO_URL}/blob/main/docs/INSTALL.md"
INSTALL_GUIDE_VI_URL = f"{REPO_URL}/blob/main/docs/INSTALL.vi.md"
USER_GUIDE_URL = f"{REPO_URL}#readme"

# (name, url) — channels that are empty are hidden in the app
DONATE = [
    ("PayPal", "https://paypal.me/PAYPAL_NAME"),
    ("Buy Me a Coffee", "https://buymeacoffee.com/BMC_NAME"),
    ("GitHub Sponsors", f"https://github.com/sponsors/{GITHUB_OWNER}"),
]


def donate_links() -> list[tuple[str, str]]:
    return [(n, u) for n, u in DONATE if u and "PAYPAL_NAME" not in u and "BMC_NAME" not in u
            and "/OWNER" not in u]
