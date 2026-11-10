"""Walters Art Museum adapter.

v1 of the Walters API closed in 2023; only static CSV data remains. We do not
ship a multi-MB CSV download, so this source reports unavailable rather than
fabricating results.
"""
def search(query, limit=20, brief=None):
    return [], "Walters API v1 closed (static data only)"