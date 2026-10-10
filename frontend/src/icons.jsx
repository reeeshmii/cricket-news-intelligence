// Simple line icons (24x24, stroke = currentColor). Decorative: always paired with a text label
// or an aria-label on the control that contains them.
const Svg = ({ children, size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {children}
  </svg>
);

export const IconHome = (p) => (
  <Svg {...p}><path d="M3 11.5 12 4l9 7.5" /><path d="M5.5 10v10h13V10" /><path d="M10 20v-5h4v5" /></Svg>
);
export const IconNews = (p) => (
  <Svg {...p}><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></Svg>
);
export const IconTopics = (p) => (
  <Svg {...p}><circle cx="12" cy="5.5" r="2.5" /><circle cx="5.5" cy="18" r="2.5" /><circle cx="18.5" cy="18" r="2.5" />
    <path d="M10.8 7.7 6.8 15.8M13.2 7.7l4 8.1M8 18h8" /></Svg>
);
export const IconBars = (p) => (
  <Svg {...p}><path d="M6 20V11M12 20V5M18 20v-6" /></Svg>
);
export const IconDoc = (p) => (
  <Svg {...p}><rect x="4" y="3.5" width="16" height="17" rx="2.5" /><path d="M8 8h8M8 12h8M8 16h5" /></Svg>
);
export const IconTrendUp = (p) => (
  <Svg {...p}><path d="M3 17l6-6 4 4 8-8" /><path d="M15 7h6v6" /></Svg>
);
export const IconDatabase = (p) => (
  <Svg {...p}><ellipse cx="12" cy="6" rx="7" ry="3" /><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6" /><path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" /></Svg>
);
export const IconRefresh = (p) => (
  <Svg {...p}><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4.5V11h-6.5" /></Svg>
);
export const IconCalendar = (p) => (
  <Svg {...p}><rect x="3.5" y="5" width="17" height="15.5" rx="2" /><path d="M3.5 9.5h17M8 3v4M16 3v4" /></Svg>
);
export const IconSearch = (p) => (
  <Svg {...p}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></Svg>
);
export const IconExternal = (p) => (
  <Svg {...p}><path d="M14 4h6v6" /><path d="M20 4 11 13" /><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></Svg>
);
export const IconInfo = (p) => (
  <Svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5M12 8h.01" /></Svg>
);
export const IconArrowRight = (p) => (
  <Svg {...p}><path d="M5 12h14M13 6l6 6-6 6" /></Svg>
);
export const IconChevronLeft = (p) => (
  <Svg {...p}><path d="m15 6-6 6 6 6" /></Svg>
);
export const IconChevronRight = (p) => (
  <Svg {...p}><path d="m9 6 6 6-6 6" /></Svg>
);
export const IconUp = (p) => (
  <Svg {...p} size={p?.size ?? 14}><path d="M12 19V5M6 11l6-6 6 6" /></Svg>
);
export const IconImage = (p) => (
  <Svg {...p}><rect x="3.5" y="5" width="17" height="14" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="m4 17 5-5 4 4 2.5-2.5L20 18" /></Svg>
);

/** Logo: a cricket bat crossing a ball, in the palette's forest and sage. */
export function LogoMark({ size = 52 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <circle cx="40" cy="26" r="17" fill="#869B7F" />
      <g transform="rotate(-40 32 32)">
        <rect x="27.5" y="6" width="9" height="34" rx="4" fill="#2E4634" />
        <rect x="30.5" y="38" width="3" height="18" rx="1.5" fill="#2E4634" />
        <path d="M30 13.5h4M30 18.5h4" stroke="#869B7F" strokeWidth="1.4" strokeLinecap="round" />
      </g>
      <circle cx="16" cy="47" r="5.5" fill="#6E9667" />
      <path d="M12.6 44.2c2.2 1.5 4.6 4.1 5.7 6.9" stroke="#FFF7EA" strokeWidth="1.2" fill="none" strokeLinecap="round" />
    </svg>
  );
}

/** Quiet stadium scene for the bottom of the sidebar (decorative, palette colours only). */
export function StadiumScene() {
  return (
    <svg className="stadium" viewBox="0 0 260 300" preserveAspectRatio="xMidYMax slice" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFF7EA" stopOpacity="0" />
          <stop offset="0.45" stopColor="#869B7F" stopOpacity="0.55" />
          <stop offset="1" stopColor="#869B7F" />
        </linearGradient>
      </defs>
      <rect width="260" height="300" fill="url(#sky)" />
      {/* birds */}
      <path d="M58 64q5-4 9 0q4-4 9 0M178 44q4-3 7 0q3-3 7 0" stroke="#6E9667" strokeWidth="1.4" fill="none" strokeLinecap="round" />
      {/* distant hills */}
      <path d="M0 150 C40 128 80 132 120 144 S200 126 260 140 V300 H0Z" fill="#869B7F" />
      {/* floodlights */}
      {[[44, 96], [212, 90]].map(([x, top]) => (
        <g key={x}>
          <rect x={x - 12} y={top} width="24" height="14" rx="2" fill="#E6D9C7" stroke="#6E9667" strokeWidth="1.2" />
          <path d={`M${x - 8} ${top + 5}h16M${x - 8} ${top + 9}h16`} stroke="#6E9667" strokeWidth="1" />
          <path d={`M${x} ${top + 14}V188`} stroke="#6E9667" strokeWidth="2.2" />
        </g>
      ))}
      {/* stands */}
      <path d="M0 178 C70 160 190 160 260 178 V208 H0Z" fill="#6E9667" opacity="0.55" />
      <path d="M0 186 C70 170 190 170 260 186" stroke="#FFF7EA" strokeWidth="1.2" fill="none" opacity="0.8" />
      <path d="M0 195 C70 180 190 180 260 195" stroke="#FFF7EA" strokeWidth="1.2" fill="none" opacity="0.8" />
      {/* outfield */}
      <ellipse cx="130" cy="262" rx="190" ry="72" fill="#6E9667" />
      <ellipse cx="130" cy="262" rx="150" ry="52" fill="#869B7F" opacity="0.55" />
      {/* pitch */}
      <path d="M118 232 h24 l8 52 h-40z" fill="#E6D9C7" />
      {/* batter */}
      <g fill="#2E4634">
        <circle cx="128" cy="236" r="3.2" />
        <rect x="125.6" y="239.5" width="5" height="11" rx="2" />
        <path d="M131 243 l7 -6" stroke="#2E4634" strokeWidth="1.8" strokeLinecap="round" />
      </g>
      {/* trees */}
      {[[14, 214, 16], [38, 222, 12], [228, 216, 15], [250, 226, 12]].map(([x, y, r]) => (
        <g key={x}><rect x={x - 1.5} y={y} width="3" height={r} fill="#2E4634" opacity="0.7" /><circle cx={x} cy={y} r={r} fill="#2E4634" opacity="0.55" /></g>
      ))}
    </svg>
  );
}
