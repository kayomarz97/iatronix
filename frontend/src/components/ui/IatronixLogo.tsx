export function IatronixLogo({ size = 28 }: { size?: number }) {
  // "Solid" treatment: brackets + ECG pulse in one weight, in the accent (theme token).
  // stroke=currentColor + color:var(--accent) so the mark tracks the active accent in light/dark.
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 512 512"
      xmlns="http://www.w3.org/2000/svg"
      style={{ display: "block", flexShrink: 0, color: "var(--accent)" }}
      aria-hidden="true"
    >
      <g
        fill="none"
        stroke="currentColor"
        strokeWidth={30}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {/* Left chevron */}
        <path d="M 150 160 L 70 256 L 150 352" />
        {/* Right chevron */}
        <path d="M 362 160 L 442 256 L 362 352" />
        {/* ECG pulse */}
        <path d="M 70 256 L 180 256 L 215 140 L 275 380 L 310 256 L 442 256" />
      </g>
    </svg>
  );
}
