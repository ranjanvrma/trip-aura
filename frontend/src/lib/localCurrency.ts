// The currency most used in each country, for the currencies the planner accepts. Countries whose own currency
// isn't supported are left out, so no suggestion is shown for them. Bulgaria uses the euro since 2026.
const COUNTRIES: Record<string, string> = {
  EUR: "AD AT BE BG CY DE EE ES FI FR GR HR IE IT LT LU LV MC ME MT NL PT SI SK SM VA XK",
  USD: "AS EC FM GU MH PA PR PW SV TL US VI",
  GBP: "GB GG IM JE", INR: "IN", AUD: "AU KI NR TV", BRL: "BR", CAD: "CA", CHF: "CH LI", CNY: "CN", CZK: "CZ",
  DKK: "DK FO GL", HKD: "HK", HUF: "HU", IDR: "ID", ILS: "IL", ISK: "IS", JPY: "JP", KRW: "KR", MXN: "MX",
  MYR: "MY", NOK: "NO SJ", NZD: "CK NU NZ", PHP: "PH", PLN: "PL", RON: "RO", SEK: "SE", SGD: "SG", THB: "TH",
  TRY: "TR", ZAR: "ZA",
};

const BY_COUNTRY = new Map(
  Object.entries(COUNTRIES).flatMap(([cur, codes]) => codes.split(" ").map((c) => [c, cur] as const)));

/** The local currency for an ISO country code, if the planner supports it. */
export function localCurrency(countryCode: string, supported: string[]): string | null {
  const cur = BY_COUNTRY.get(countryCode.toUpperCase());
  return cur && supported.includes(cur) ? cur : null;
}
