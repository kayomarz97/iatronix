export function IatronixLogo({ size = 28 }: { size?: number }) {
  const scale = size / 512;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 512 512"
      xmlns="http://www.w3.org/2000/svg"
      style={{ display: "block", flexShrink: 0 }}
      aria-hidden="true"
    >
      <defs>
        <filter id="logo-glow-s" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation={8 / scale} result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="logo-glow-p" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation={12 / scale} result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {/* Left chevron */}
      <path
        d="M 150 160 L 70 256 L 150 352"
        stroke="#818CF8"
        fill="none"
        strokeWidth="28"
        strokeLinecap="round"
        strokeLinejoin="round"
        filter="url(#logo-glow-s)"
      />
      {/* Right chevron */}
      <path
        d="M 362 160 L 442 256 L 362 352"
        stroke="#818CF8"
        fill="none"
        strokeWidth="28"
        strokeLinecap="round"
        strokeLinejoin="round"
        filter="url(#logo-glow-s)"
      />
      {/* Waveform */}
      <path
        d="M 70 256 L 180 256 L 215 140 L 275 380 L 310 256 L 442 256"
        stroke="#22D3EE"
        fill="none"
        strokeWidth="28"
        strokeLinecap="round"
        strokeLinejoin="round"
        filter="url(#logo-glow-p)"
      />
    </svg>
  );
}
