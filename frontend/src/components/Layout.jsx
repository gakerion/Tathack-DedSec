import { useState } from "react";
import { Outlet } from "react-router-dom";
import Navbar from "./Navbar";
import Commits from "./Commits";

function Layout() {
  const [hasChat, setHasChat] = useState(false);

  return (
    <div className="app-shell">
      <Navbar />

      <div className="app-layout">
        <main className="chat-content">
          <Outlet context={{ setHasChat }} />
        </main>

        {hasChat && <Commits />}
      </div>
    </div>
  );
}

export default Layout;