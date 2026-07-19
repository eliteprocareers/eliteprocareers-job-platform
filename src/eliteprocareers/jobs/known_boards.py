"""
Curated list of known large employers on Greenhouse's public Job Board API.

MVP approach per project scope: pull broadly from known employers rather
than a company-search flow. Not exhaustive — board tokens can go stale if
a company migrates ATS, which the ingestion script tolerates per-board
rather than failing the whole run.

Confirmed working tokens as of this session (2026-07-19):
stripe, airbnb, doordashusa, robinhood, coinbase, reddit, discord, figma,
asana, pinterest, gitlab, twilio, cloudflare, dropbox, squarespace.
Dropped: 'notion' (moved off Greenhouse to a different ATS), 'etsy'
(token unconfirmed — worth re-checking later rather than guessing).
"""

GREENHOUSE_BOARDS = {
    "stripe": "Stripe",
    "airbnb": "Airbnb",
    "doordashusa": "DoorDash",
    "robinhood": "Robinhood",
    "coinbase": "Coinbase",
    "reddit": "Reddit",
    "discord": "Discord",
    "figma": "Figma",
    "asana": "Asana",
    "pinterest": "Pinterest",
    "gitlab": "GitLab",
    "twilio": "Twilio",
    "cloudflare": "Cloudflare",
    "dropbox": "Dropbox",
    "squarespace": "Squarespace",
}
