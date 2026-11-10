"""Adapters: each search(query, limit) -> (items, error). Item dict: id,title,date_str,creator,source,image_url,thumb_url,page_url,medium,extra."""
from .loc import search as search_loc
from .nga import search as search_nga
from .europeana import search as search_europeana
from .met import search as search_met
from .commons import search as search_commons
from .cleveland import search as search_cleveland
from .artic import search as search_artic
from .wellcome import search as search_wellcome
from .harvard import search as search_harvard
from .openverse import search as search_openverse
from .smk import search as search_smk
from .rijks import search as search_rijks
from .mia import search as search_mia
from .ia import search as search_ia
from .walters import search as search_walters

# Every source must carry verifiable dates in its metadata (OpenVerse was
# removed: no artwork dates, only index timestamps).
ADAPTERS = {
    "NGA": search_nga,
    "LOC": search_loc,
    "Europeana": search_europeana,
    "Met": search_met,
    "Commons": search_commons,
    "Cleveland": search_cleveland,
    "AIC": search_artic,
    "Wellcome": search_wellcome,
    "Harvard": search_harvard,
    "OpenVerse": search_openverse,
    "SMK": search_smk,
    "Rijksmuseum": search_rijks,
    "Mia": search_mia,
    "InternetArchive": search_ia,
    "BHL": search_bhl,
    "Walters": search_walters,
}


