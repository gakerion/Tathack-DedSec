import { NavLink } from "react-router-dom";
import brand from "../assets/honeygate.png";
import "./Navbar.css";

function Navbar() {
  return (
    <header className="navbar-header">
      <NavLink to="/" aria-label="HoneyGate home">
        <img
          src={brand}
          alt="HoneyGate"
          className="navbar-brand"
        />
      </NavLink>

      <nav className="navbar" aria-label="Main navigation">
        <NavLink to="/" end>
          Chat
        </NavLink>

        <NavLink to="/how-to-use">
          How to Use
        </NavLink>

        <NavLink to="/about">
          About Us
        </NavLink>
      </nav>
    </header>
  );
}

export default Navbar;