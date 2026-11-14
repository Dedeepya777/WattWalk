/** WattWalk mark: an apartment building with a leaf growing beside it (Charcoal, Moss, Forest). */
export function Logo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect x="4" y="8" width="14" height="21" rx="2.5" fill="#282d28" />
      <g fill="#f9f8f5">
        <rect x="7" y="12" width="3" height="3" rx="0.6" />
        <rect x="12" y="12" width="3" height="3" rx="0.6" />
        <rect x="7" y="17" width="3" height="3" rx="0.6" />
        <rect x="12" y="17" width="3" height="3" rx="0.6" />
        <rect x="9.5" y="23" width="3" height="6" rx="0.6" />
      </g>
      <path d="M16 29C15.5 17 21 8.5 29.5 4.5C30 15 25.5 25 16 29Z" fill="#a4b39a" />
      <path d="M17.5 27C20 19 23 13 27.5 8" stroke="#465b47" strokeWidth="1.3" strokeLinecap="round" fill="none" />
    </svg>
  );
}
