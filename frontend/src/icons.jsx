// Simple line icons (24x24, stroke = currentColor), decorative: always paired with a text label.
const Svg = ({ children, size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {children}
  </svg>
);

export const IconOverview = (p) => (
  <Svg {...p}><rect x="3" y="3" width="7" height="8" rx="2" /><rect x="14" y="3" width="7" height="5" rx="2" />
    <rect x="14" y="12" width="7" height="9" rx="2" /><rect x="3" y="15" width="7" height="6" rx="2" /></Svg>
);
export const IconNews = (p) => (
  <Svg {...p}><path d="M5 4h11a2 2 0 0 1 2 2v13a1 1 0 0 0 2 0V9" /><path d="M5 4a1 1 0 0 0-1 1v14a2 2 0 0 0 2 2h13" />
    <path d="M8 8h6M8 12h6M8 16h3" /></Svg>
);
export const IconTopics = (p) => (
  <Svg {...p}><circle cx="6" cy="7" r="2.5" /><circle cx="17" cy="6" r="2.5" /><circle cx="12" cy="17" r="2.5" />
    <path d="M8.3 8.2 10.8 15M15.6 8.1l-2.4 6.7M8.5 7h6" /></Svg>
);
export const IconTrend = (p) => (
  <Svg {...p}><path d="M3 17l6-6 4 4 8-8" /><path d="M15 7h6v6" /></Svg>
);
export const IconArticles = (p) => (
  <Svg {...p}><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6M9 12h6M9 16h4" /></Svg>
);
export const IconNew = (p) => (
  <Svg {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" /></Svg>
);
export const IconRefresh = (p) => (
  <Svg {...p}><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 5v6h-6" /></Svg>
);
export const IconUp = (p) => (
  <Svg {...p}><path d="M12 19V5M6 11l6-6 6 6" /></Svg>
);
export const IconChevron = (p) => (
  <Svg {...p}><path d="m6 9 6 6 6-6" /></Svg>
);
