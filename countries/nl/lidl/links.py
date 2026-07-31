"""Lidl NL category seeds for full-site leaf discovery.

Lidl.nl product pages live under leaf URLs (`/h/{slug}/h…`). We discover those
leaves from the main menu departments at scrape time. Pagination uses
`?offset=N` in steps of 48.
"""

# Main shop departments from lidl.nl nav (screenshot / live menu).
SEED_CATEGORY_URLS = [
    "https://www.lidl.nl/c/eten-en-drinken/s10068374",
    "https://www.lidl.nl/c/koken-huishouden/s10067764",
    "https://www.lidl.nl/c/klussen-tuin/s10067761",
    "https://www.lidl.nl/c/sport-vrije-tijd/s10067763",
    "https://www.lidl.nl/c/wonen-inrichting/s10067762",
    "https://www.lidl.nl/c/mode-accessoires/s10067765",
    "https://www.lidl.nl/c/baby-kind-speelgoed/s10067767",
    "https://www.lidl.nl/c/alles-huishouden/s10046769",
    "https://www.lidl.nl/c/alles-tuin/s10019372",
]

# Skip legal / account / content hubs that are not product departments.
SKIP_MAIN_SLUGS = {
    "algemene-voorwaarden",
    "complaince",
    "cookielijst",
    "duurzaamheid-in-de-online-shop",
    "gegevensbescherming-op-onze-websites",
    "herroepingsrecht",
    "impressum",
    "lidl-plus",
    "lidl-plus-algemene-voorwaarden",
    "lidl-plus-extra-voordeel",
    "lidl-plus-privacy",
    "nieuwsbrief-aanmelden",
    "nieuwsbrief-aanmelden-overige",
    "privacy-cookie-verklaring",
    "service-contact-folders",
    "service-contact-spam",
    "toegankelijkheidsverklaring",
    "redirect-sale-page",
}

# Fallback grocery leaves if discovery fails entirely.
FALLBACK_LEAF_URLS = [
    "https://www.lidl.nl/h/bakkerij/h10096086",
    "https://www.lidl.nl/h/bloemen-planten/h10071024",
    "https://www.lidl.nl/h/diepvries/h10071049",
    "https://www.lidl.nl/h/dranken/h10071022",
    "https://www.lidl.nl/h/drogisterij-verzorging/h10096275",
    "https://www.lidl.nl/h/groente-fruit/h10071012",
    "https://www.lidl.nl/h/huishouden/h10096287",
    "https://www.lidl.nl/h/kaas-zuivel-eieren/h10095761",
    "https://www.lidl.nl/h/kant-en-klaar-maaltijden/h10071020",
    "https://www.lidl.nl/h/koffie-thee-cacao/h10071683",
    "https://www.lidl.nl/h/ontbijtgranen-broodbeleg/h10096153",
    "https://www.lidl.nl/h/sauzen-olie-kruiden/h10096110",
    "https://www.lidl.nl/h/snoep-snacks/h10096205",
    "https://www.lidl.nl/h/vlees-gevogelte/h10095752",
    "https://www.lidl.nl/h/voorraadkast/h10096095",
    "https://www.lidl.nl/h/wijn-bier-sterke-drank/h10096268",
    "https://www.lidl.nl/h/benodigdheden-voor-huisdieren/h10067551",
]

OFFSET_STEP = 48
MAX_OFFSET = 960  # safety cap (~20 pages)

# Back-compat for anything that still imports `links`.
links = list(FALLBACK_LEAF_URLS)

# Kept for older imports; discovery no longer filters to grocery-only.
GROCERY_LEAF_SLUGS = {
    "bakkerij",
    "benodigdheden-voor-huisdieren",
    "bloemen-planten",
    "diepvries",
    "dranken",
    "drogisterij-verzorging",
    "groente-fruit",
    "huishouden",
    "kaas-zuivel-eieren",
    "kant-en-klaar-maaltijden",
    "koffie-thee-cacao",
    "ontbijtgranen-broodbeleg",
    "sauzen-olie-kruiden",
    "snoep-snacks",
    "vlees-gevogelte",
    "voorraadkast",
    "wijn-bier-sterke-drank",
}
