import { NavLink, Route, Routes } from "react-router-dom";
import { IconNews, IconOverview, IconTopics, IconTrend } from "./icons.jsx";
import Overview from "./pages/Overview.jsx";
import LatestNews from "./pages/LatestNews.jsx";
import Explorer from "./pages/Explorer.jsx";
import Trending from "./pages/Trending.jsx";

const SECTIONS = [
  { to: "/", label: "Overview", icon: IconOverview, end: true },
  { to: "/news", label: "Latest News", icon: IconNews },
  { to: "/topics", label: "Topic & Cluster Explorer", icon: IconTopics },
  { to: "/trends", label: "Trending Topics", icon: IconTrend },
];

export default function App() {
  return (
    <div className="app">
      <aside className="sidebar">
        <NavLink to="/" className="logo" aria-label="T20 News Intelligence, overview">
          <span className="logo-mark" aria-hidden="true">T20</span>
          <span className="logo-text">News Intelligence</span>
        </NavLink>
        <nav aria-label="Sections">
          <p className="menu-label">Menu</p>
          <div className="menu">
            {SECTIONS.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end}>
                <Icon />
                {label}
              </NavLink>
            ))}
          </div>
        </nav>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/news" element={<LatestNews />} />
          <Route path="/topics" element={<Explorer />} />
          <Route path="/trends" element={<Trending />} />
          <Route path="*" element={<Overview />} />
        </Routes>
      </main>
    </div>
  );
}
