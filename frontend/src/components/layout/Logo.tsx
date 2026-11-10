/** Brand mark: a route line through three stops inside a soft square. Same drawing as public/favicon.svg. */
export default function Logo() {
  return (
    <svg width={26} height={26} viewBox="0 0 32 32" aria-hidden className="logo">
      <rect x="1" y="1" width="30" height="30" rx="9" fill="#2f3a33" />
      <path d="M8 22c3-8 6-1 9-6s5-6 7-6" fill="none" stroke="#f6efe3" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="8" cy="22" r="2.6" fill="#cfe2cf" />
      <circle cx="16.5" cy="16" r="2.2" fill="#f2d9bf" />
      <circle cx="24" cy="10" r="2.6" fill="#cfe0ee" />
    </svg>
  );
}
