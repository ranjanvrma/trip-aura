/** Brand mark: a route line through three stops on a night-sky square. Same drawing as public/favicon.svg. */
export default function Logo() {
  return (
    <svg width={26} height={26} viewBox="0 0 32 32" aria-hidden className="logo">
      <rect x="1" y="1" width="30" height="30" rx="9" fill="#111922" stroke="#33414f" />
      <path d="M8 22c3-8 6-1 9-6s5-6 7-6" fill="none" stroke="#f3efe6" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="8" cy="22" r="2.6" fill="#6fe3cf" />
      <circle cx="16.5" cy="16" r="2.2" fill="#f2c26b" />
      <circle cx="24" cy="10" r="2.6" fill="#ff8f66" />
    </svg>
  );
}
