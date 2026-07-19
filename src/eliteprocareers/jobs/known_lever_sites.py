"""
Curated list of known employers on Lever's public Postings API.

Same MVP approach as known_boards.py for Greenhouse — a curated list
rather than a company-search flow, since Lever has no public directory
of its customers either.

Confirmed working tokens as of this session (2026-07-19):
netflix, kraken, rackspace, meesho — all return 200 OK. netflix, kraken,
and rackspace currently have zero open postings (empty array, not a
broken token — confirmed live). meesho is the only one with real open
postings right now, which is expected to change over time as these
companies' hiring activity fluctuates.
Dropped: eventbrite, reddit-postings, robinhood-lever, doordash, brex,
xero, 500global, welocalize, upstox — all 404'd, meaning either wrong
site slug or that company isn't actually on Lever. Worth re-checking
individually later rather than guessing again.
"""

LEVER_SITES = {
    "netflix": "Netflix",
    "kraken": "Kraken",
    "rackspace": "Rackspace Technology",
    "meesho": "Meesho",
}
