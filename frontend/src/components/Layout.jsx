import { Outlet } from "react-router-dom";
import Navbar from "./Navbar";
import Commits from "./Commits";

function Layout() {
  return (
    <div className="app-shell">
      <Navbar />

      <div className="app-layout">
        <main className="chat-content">
          <Outlet />
        </main>

        <Commits />
      </div>
    </div>
  );
}

export default Layout;