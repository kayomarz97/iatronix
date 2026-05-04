"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ChevronDown,
  LogOut,
  Settings,
  User,
  Menu,
  X,
} from "lucide-react";
import { signOut } from "firebase/auth";
import { auth } from "@/lib/firebase";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";
import { IatronixLogo } from "@/components/ui/IatronixLogo";

const NAV_LINKS = [
  { href: "/", label: "Search" },
  { href: "/waves", label: "Waves" },
  { href: "/about", label: "About" },
];

export function Header() {
  const pathname = usePathname();
  const [email, setEmail] = useState("");
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const storedKey = localStorage.getItem(API_KEY_STORAGE_KEY);
    setIsLoggedIn(!!storedKey);
    setEmail(localStorage.getItem("iatronix_email") || "");
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const logout = async () => {
    await signOut(auth);
    localStorage.removeItem(API_KEY_STORAGE_KEY);
    localStorage.removeItem("iatronix_email");
    window.location.href = "/login";
  };

  const displayName = email
    ? email.split("@")[0]
    : "Account";

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <header
      style={{
        background: "var(--bg-surface)",
        borderBottom: "1px solid var(--border)",
        position: "sticky",
        top: 0,
        zIndex: 40,
        backdropFilter: "blur(8px)",
      }}
    >
      <div
        style={{
          maxWidth: 1100,
          margin: "0 auto",
          padding: "0 1.25rem",
          height: 58,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
        }}
      >
        {/* Logo */}
        <Link
          href="/"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            fontWeight: 700,
            fontSize: "1.1rem",
            color: "var(--text-primary)",
            textDecoration: "none",
            flexShrink: 0,
          }}
        >
          <IatronixLogo size={28} />
          Iatronix
        </Link>

        {/* Center nav — desktop only */}
        <nav
          style={{
            display: "flex",
            gap: "1.5rem",
            alignItems: "center",
          }}
          className="header-nav-desktop"
        >
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`nav-tab ${isActive(link.href) ? "active" : ""}`}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        {/* Right side */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {/* Auth area */}
          {isLoggedIn ? (
            <div ref={dropdownRef} style={{ position: "relative" }}>
              <button
                onClick={() => setDropdownOpen(!dropdownOpen)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.375rem",
                  padding: "6px 12px",
                  background: "transparent",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-md)",
                  cursor: "pointer",
                  color: "var(--text-secondary)",
                  fontSize: "0.875rem",
                  fontWeight: 500,
                  transition: "all var(--transition)",
                }}
                onMouseOver={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = "var(--bg-hover)";
                  (e.currentTarget as HTMLButtonElement).style.color = "var(--text-primary)";
                }}
                onMouseOut={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                  (e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)";
                }}
              >
                <User size={15} />
                <span style={{ maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {displayName}
                </span>
                <ChevronDown
                  size={14}
                  style={{
                    transition: "transform var(--transition)",
                    transform: dropdownOpen ? "rotate(180deg)" : "rotate(0deg)",
                  }}
                />
              </button>

              {dropdownOpen && (
                <div
                  className="animate-in"
                  style={{
                    position: "absolute",
                    top: "calc(100% + 6px)",
                    right: 0,
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-md)",
                    boxShadow: "var(--shadow-lg)",
                    minWidth: 180,
                    overflow: "hidden",
                    zIndex: 50,
                  }}
                >
                  <DropdownItem href="/settings" icon={<Settings size={15} />} label="Settings" onClick={() => setDropdownOpen(false)} />
                  <div style={{ height: 1, background: "var(--border)", margin: "4px 0" }} />
                  <DropdownButton icon={<LogOut size={15} />} label="Sign Out" onClick={logout} danger />
                </div>
              )}
            </div>
          ) : (
            <Link
              href="/login"
              style={{
                padding: "6px 16px",
                background: "var(--accent)",
                color: "#fff",
                borderRadius: "var(--radius-md)",
                fontSize: "0.875rem",
                fontWeight: 500,
                textDecoration: "none",
                transition: "background var(--transition), transform var(--transition)",
              }}
              onMouseOver={(e) => {
                (e.currentTarget as HTMLAnchorElement).style.background = "var(--accent-hover)";
              }}
              onMouseOut={(e) => {
                (e.currentTarget as HTMLAnchorElement).style.background = "var(--accent)";
              }}
            >
              Sign In
            </Link>
          )}

          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="header-hamburger"
            aria-label="Toggle menu"
            style={{
              display: "none",
              background: "transparent",
              border: "none",
              cursor: "pointer",
              padding: "8px",
              borderRadius: "var(--radius-md)",
              color: "var(--text-secondary)",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {/* Mobile nav menu */}
      {mobileMenuOpen && (
        <div
          className="animate-in"
          style={{
            borderTop: "1px solid var(--border)",
            background: "var(--bg-surface)",
            padding: "0.75rem 1.25rem 1rem",
          }}
        >
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMobileMenuOpen(false)}
              style={{
                display: "block",
                padding: "0.625rem 0",
                color: isActive(link.href) ? "var(--accent)" : "var(--text-secondary)",
                fontWeight: isActive(link.href) ? 600 : 500,
                textDecoration: "none",
                fontSize: "0.95rem",
                borderBottom: "1px solid var(--border)",
              }}
            >
              {link.label}
            </Link>
          ))}
        </div>
      )}

      <style>{`
        @media (max-width: 640px) {
          .header-nav-desktop { display: none !important; }
          .header-hamburger { display: flex !important; }
        }
      `}</style>
    </header>
  );
}

function DropdownItem({
  href,
  icon,
  label,
  onClick,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.625rem",
        padding: "8px 14px",
        color: "var(--text-secondary)",
        textDecoration: "none",
        fontSize: "0.875rem",
        transition: "background var(--transition), color var(--transition)",
      }}
      onMouseOver={(e) => {
        (e.currentTarget as HTMLAnchorElement).style.background = "var(--bg-hover)";
        (e.currentTarget as HTMLAnchorElement).style.color = "var(--text-primary)";
      }}
      onMouseOut={(e) => {
        (e.currentTarget as HTMLAnchorElement).style.background = "transparent";
        (e.currentTarget as HTMLAnchorElement).style.color = "var(--text-secondary)";
      }}
    >
      {icon}
      {label}
    </Link>
  );
}

function DropdownButton({
  icon,
  label,
  onClick,
  danger,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.625rem",
        padding: "8px 14px",
        width: "100%",
        background: "transparent",
        border: "none",
        cursor: "pointer",
        color: danger ? "var(--danger)" : "var(--text-secondary)",
        fontSize: "0.875rem",
        textAlign: "left",
        transition: "background var(--transition)",
      }}
      onMouseOver={(e) => {
        (e.currentTarget as HTMLButtonElement).style.background = "var(--bg-hover)";
      }}
      onMouseOut={(e) => {
        (e.currentTarget as HTMLButtonElement).style.background = "transparent";
      }}
    >
      {icon}
      {label}
    </button>
  );
}
