"use client";

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

interface PasswordInputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function PasswordInput({ label, style, ...props }: PasswordInputProps) {
  const [show, setShow] = useState(false);

  return (
    <div style={{ width: "100%" }}>
      {label && (
        <label
          style={{
            display: "block",
            fontSize: "0.875rem",
            fontWeight: 500,
            color: "var(--text-secondary)",
            marginBottom: "0.375rem",
          }}
        >
          {label}
        </label>
      )}
      <div style={{ position: "relative" }}>
        <input
          {...props}
          type={show ? "text" : "password"}
          style={{
            width: "100%",
            padding: "10px 42px 10px 14px",
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-md)",
            color: "var(--text-primary)",
            fontSize: "0.95rem",
            outline: "none",
            transition: "border-color var(--transition), box-shadow var(--transition)",
            boxSizing: "border-box",
            ...style,
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = "var(--border-focus)";
            e.currentTarget.style.boxShadow = "0 0 0 3px var(--accent-glow)";
            props.onFocus?.(e);
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = "var(--border)";
            e.currentTarget.style.boxShadow = "none";
            props.onBlur?.(e);
          }}
        />
        <button
          type="button"
          onClick={() => setShow(!show)}
          tabIndex={-1}
          style={{
            position: "absolute",
            right: "10px",
            top: "50%",
            transform: "translateY(-50%)",
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--text-muted)",
            padding: "4px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transition: "color var(--transition)",
          }}
          onMouseOver={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)";
          }}
          onMouseOut={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color = "var(--text-muted)";
          }}
          aria-label={show ? "Hide password" : "Show password"}
        >
          {show ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>
    </div>
  );
}
