"""Currencies the app accepts, and the currency most used in each country.

Rates come from the European Central Bank (via Frankfurter) where it publishes one, and from ExchangeRate-API's open
endpoint for every other currency (see services/fx_service.py).
"""

# ISO 3166 country code -> the currency travellers mostly pay in there. Where a second currency is in everyday use
# (Panama, Zimbabwe, Timor-Leste...), the one shops and hotels quote is listed. Bulgaria uses the euro since 2026.
_BY_CURRENCY = {
    "EUR": "AD AT AX BE BG BL CY DE EE ES FI FR GF GP GR HR IE IT LT LU LV MC ME MF MQ MT NL PM PT RE SI SK SM TF "
           "VA XK YT",
    "USD": "AS BQ EC FM GU IO MH MP PA PR PW SV TC TL UM US VG VI ZW",
    "XCD": "AG AI DM GD KN LC MS VC", "XOF": "BF BJ CI GW ML NE SN TG", "XAF": "CF CG CM GA GQ TD",
    "XPF": "NC PF WF", "AUD": "AU CC CX KI NF NR TV", "NZD": "CK NU NZ PN TK", "GBP": "GB GG IM JE",
    "DKK": "DK FO GL", "NOK": "NO SJ", "CHF": "CH LI", "MAD": "EH MA", "ILS": "IL PS", "XCG": "CW SX",
    "AED": "AE", "AFN": "AF", "ALL": "AL", "AMD": "AM", "AOA": "AO", "ARS": "AR", "AWG": "AW", "AZN": "AZ",
    "BAM": "BA", "BBD": "BB", "BDT": "BD", "BHD": "BH", "BIF": "BI", "BMD": "BM", "BND": "BN", "BOB": "BO",
    "BRL": "BR", "BSD": "BS", "BTN": "BT", "BWP": "BW", "BYN": "BY", "BZD": "BZ", "CAD": "CA", "CDF": "CD",
    "CLP": "CL", "CNY": "CN", "COP": "CO", "CRC": "CR", "CUP": "CU", "CVE": "CV", "CZK": "CZ", "DJF": "DJ",
    "DOP": "DO", "DZD": "DZ", "EGP": "EG", "ERN": "ER", "ETB": "ET", "FJD": "FJ", "FKP": "FK", "GEL": "GE",
    "GHS": "GH", "GIP": "GI", "GMD": "GM", "GNF": "GN", "GTQ": "GT", "GYD": "GY", "HKD": "HK", "HNL": "HN",
    "HTG": "HT", "HUF": "HU", "IDR": "ID", "INR": "IN", "IQD": "IQ", "IRR": "IR", "ISK": "IS", "JMD": "JM",
    "JOD": "JO", "JPY": "JP", "KES": "KE", "KGS": "KG", "KHR": "KH", "KMF": "KM", "KRW": "KR", "KWD": "KW",
    "KYD": "KY", "KZT": "KZ", "LAK": "LA", "LBP": "LB", "LKR": "LK", "LRD": "LR", "LSL": "LS", "LYD": "LY",
    "MDL": "MD", "MGA": "MG", "MKD": "MK", "MMK": "MM", "MNT": "MN", "MOP": "MO", "MRU": "MR", "MUR": "MU",
    "MVR": "MV", "MWK": "MW", "MXN": "MX", "MYR": "MY", "MZN": "MZ", "NAD": "NA", "NGN": "NG", "NIO": "NI",
    "NPR": "NP", "OMR": "OM", "PEN": "PE", "PGK": "PG", "PHP": "PH", "PKR": "PK", "PLN": "PL", "PYG": "PY",
    "QAR": "QA", "RON": "RO", "RSD": "RS", "RUB": "RU", "RWF": "RW", "SAR": "SA", "SBD": "SB", "SCR": "SC",
    "SDG": "SD", "SEK": "SE", "SGD": "SG", "SHP": "SH", "SLE": "SL", "SOS": "SO", "SRD": "SR", "SSP": "SS",
    "STN": "ST", "SYP": "SY", "SZL": "SZ", "THB": "TH", "TJS": "TJ", "TMT": "TM", "TND": "TN", "TOP": "TO",
    "TRY": "TR", "TTD": "TT", "TWD": "TW", "TZS": "TZ", "UAH": "UA", "UGX": "UG", "UYU": "UY", "UZS": "UZ",
    "VES": "VE", "VND": "VN", "VUV": "VU", "WST": "WS", "YER": "YE", "ZAR": "ZA", "ZMW": "ZM",
}
COUNTRY_CURRENCY: dict[str, str] = {c: cur for cur, codes in _BY_CURRENCY.items() for c in codes.split()}

# The most chosen currencies first, then every other one alphabetically.
_COMMON = ("USD", "EUR", "GBP", "INR", "JPY", "AUD", "CAD", "CHF", "CNY", "AED", "SGD")
SUPPORTED_CURRENCIES: tuple[str, ...] = _COMMON + tuple(sorted(set(_BY_CURRENCY) - set(_COMMON)))


def currency_for_country(country_code: str) -> str | None:
    return COUNTRY_CURRENCY.get(country_code.upper())
