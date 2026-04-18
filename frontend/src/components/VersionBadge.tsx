import React from "react";

export const VersionBadge: React.FC = () => {
  const version = process.env.NEXT_PUBLIC_FRONTEND_VERSION ?? "v2.1";

  const style: React.CSSProperties = {
    position: "fixed",
    bottom: "12px",
    right: "12px",
    padding: "4px 8px",
    background: "rgba(0,0,0,0.6)",
    color: "#fff",
    borderRadius: "4px",
    fontSize: "0.85rem",
    fontFamily: "system-ui, sans-serif",
    zIndex: 9999,
    pointerEvents: "none",
    opacity: 0.85,
  };

  return <div style={style}>v{version}</div>;
};
