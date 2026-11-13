// Where the sun is overhead right now, accurate to well under a degree, which is far finer than the soft
// day/night edge drawn on the globe. Standard low-precision approximations, no ephemeris needed:
//   declination  = -23.44 deg * cos(360/365 * (days since 1 January + 10))
//   longitude    = -15 deg per hour away from 12:00 UTC, corrected by the equation of time
//   equation of time (minutes) = 9.87 sin 2B - 7.53 cos B - 1.5 sin B, B = 360/364 * (day of year - 81)

const DEG = Math.PI / 180;
const DAY_MS = 86_400_000;

export function subsolarPoint(date: Date): { lat: number; lng: number } {
  const startOfYear = Date.UTC(date.getUTCFullYear(), 0, 1);
  const days = (date.getTime() - startOfYear) / DAY_MS; // fractional days since 1 January 00:00 UTC

  const lat = -23.44 * Math.cos((360 / 365) * (days + 10) * DEG);

  const b = (360 / 364) * (days + 1 - 81) * DEG;
  const equationOfTime = 9.87 * Math.sin(2 * b) - 7.53 * Math.cos(b) - 1.5 * Math.sin(b);
  const utcHours = date.getUTCHours() + date.getUTCMinutes() / 60 + date.getUTCSeconds() / 3600;
  const raw = -15 * (utcHours - 12 + equationOfTime / 60);
  const lng = ((((raw + 180) % 360) + 360) % 360) - 180;

  return { lat, lng };
}
