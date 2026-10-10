import { NavLink, Route, Routes } from "react-router-dom";
import { IconBars, IconHome, IconNews, IconTopics, LogoMark, StadiumScene } from "./icons.jsx";
import Overview from "./pages/Overview.jsx";
import LatestNews from "./pages/LatestNews.jsx";
import Explorer from "./pages/Explorer.jsx";
import Trending from "./pages/Trending.jsx";

const SECTIONS = [
  { to: "/", label: "Overview", icon: IconHome, end: true },
  { to: "/news", label: "Latest News", icon: IconNews },
  { to: "/topics", label: "Topic & Cluster Explorer", icon: IconTopics },
  { to: "/trends", label: "Trending Topics", icon: IconBars },
];

export default function App() {
  return (
    <div className="app">
      <aside className="sidebar">
        <NavLink to="/" className="logo" aria-label="T20 News Intelligence, overview">
          <LogoMark />
          <span className="logo-text">
            <span className="l1">T20</span>
            <span className="l2">News Intelligence</span>
            <span className="l3">News • Topics • Trends</span>
          </span>
        </NavLink>
        <nav className="menu" aria-label="Sections">
          {SECTIONS.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}>
              <Icon />
              {label}
            </NavLink>
          ))}
        </nav>
        <StadiumScene />
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
