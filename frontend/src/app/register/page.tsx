"use client";

import { useState } from "react";
import Link from "next/link";
import { Activity, Mail, ChevronRight, ExternalLink, Check } from "lucide-react";
import { PasswordInput } from "@/components/ui/PasswordInput";

type Step = 1 | 2 | 3;

const POSITIONS = [
  "Medical Student",
  "Intern",
  "Junior Resident",
  "Senior Resident",
  "Fellow",
  "Consultant/Attending",
  "Researcher",
  "Nursing Staff",
  "Pharmacist",
  "Allied Health Professional",
  "Other",
];

const SPECIALTIES = [
  "Cardiology", "Oncology", "Neurology", "Pulmonology", "Gastroenterology",
  "Endocrinology", "Nephrology", "Rheumatology", "Infectious Disease",
  "Emergency Medicine", "Critical Care", "General Medicine", "Surgery",
  "Pediatrics", "Obstetrics & Gynecology", "Psychiatry", "Radiology",
  "Dermatology", "Ophthalmology", "Orthopaedics", "ENT", "Urology",
  "Hematology", "Palliative Care", "Other",
];

const INSTITUTION_TYPES = [
  "Government Hospital",
  "Private Hospital",
  "Academic/Teaching",
  "Research Institute",
  "Other",
];

export default function RegisterPage() {
  const [step, setStep] = useState<Step>(1);

  // Step 1 fields
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  // Step 2 fields
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [country, setCountry] = useState("");
  const [position, setPosition] = useState("");
  const [institute, setInstitute] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [specialtyInput, setSpecialtyInput] = useState("");
  const [showSpecialtySuggestions, setShowSpecialtySuggestions] = useState(false);
  const [institutionType, setInstitutionType] = useState("");
  const [newsletter, setNewsletter] = useState(false);

  // Step 3 fields
  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [activeKeyTab, setActiveKeyTab] = useState<"anthropic" | "openai">("anthropic");

  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleStep1 = (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setError(null);
    setStep(2);
  };

  const handleStep2 = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) {
      setError("Username is required");
      return;
    }
    setError(null);
    setStep(3);
  };

  const handleStep3 = async (skip = false) => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password,
          username,
          full_name: fullName || undefined,
          country: country || undefined,
          position: position || undefined,
          institute: institute || undefined,
          specialty: specialty || undefined,
          institution_type: institutionType || undefined,
          newsletter_consent: newsletter,
          anthropic_key: skip ? undefined : anthropicKey || undefined,
          openai_key: skip ? undefined : openaiKey || undefined,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || "Registration failed");
        return;
      }

      window.location.href = "/login?registered=1";
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const filteredSpecialties = SPECIALTIES.filter((s) =>
    s.toLowerCase().includes(specialtyInput.toLowerCase())
  );

  return (
    <div
      style={{
        minHeight: "calc(100vh - 110px)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        padding: "3rem 1rem",
      }}
    >
      <div
        className="animate-in"
        style={{
          width: "100%",
          maxWidth: 480,
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-lg)",
          padding: "2.5rem 2rem",
        }}
      >
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: "50%",
              background: "var(--accent-glow)",
              border: "1px solid rgba(59,130,246,0.3)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 1rem",
            }}
          >
            <Activity size={20} color="var(--accent)" />
          </div>
          <h1
            style={{
              margin: "0 0 0.25rem",
              fontSize: "1.4rem",
              fontWeight: 700,
              color: "var(--text-primary)",
            }}
          >
            {step === 1 && "Create your account"}
            {step === 2 && "Tell us about yourself"}
            {step === 3 && "Connect your AI provider"}
          </h1>
          {step === 2 && (
            <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-muted)" }}>
              This helps personalize your experience
            </p>
          )}
          {step === 3 && (
            <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-muted)" }}>
              Your key is encrypted and stored securely
            </p>
          )}
        </div>

        {/* Step indicator */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "0.5rem",
            marginBottom: "1.75rem",
          }}
        >
          {([1, 2, 3] as Step[]).map((s) => (
            <div key={s} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: "50%",
                  background: s < step
                    ? "var(--success)"
                    : s === step
                    ? "var(--accent)"
                    : "var(--bg-elevated)",
                  border: `2px solid ${s <= step ? (s < step ? "var(--success)" : "var(--accent)") : "var(--border)"}`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  color: s <= step ? "#fff" : "var(--text-muted)",
                  transition: "all var(--transition)",
                }}
              >
                {s < step ? <Check size={14} /> : s}
              </div>
              {s < 3 && (
                <div
                  style={{
                    width: 36,
                    height: 2,
                    background: s < step ? "var(--success)" : "var(--border)",
                    borderRadius: 1,
                    transition: "background var(--transition)",
                  }}
                />
              )}
            </div>
          ))}
        </div>

        {/* Error */}
        {error && (
          <div
            style={{
              marginBottom: "1rem",
              padding: "0.75rem 1rem",
              background: "rgba(239,68,68,0.1)",
              border: "1px solid rgba(239,68,68,0.3)",
              borderRadius: "var(--radius-md)",
              fontSize: "0.875rem",
              color: "var(--danger)",
            }}
          >
            {error}
          </div>
        )}

        {/* ── Step 1 ── */}
        {step === 1 && (
          <form onSubmit={handleStep1} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div>
              <label style={labelStyle}>Email</label>
              <div style={{ position: "relative" }}>
                <Mail
                  size={16}
                  style={{
                    position: "absolute", left: 14, top: "50%",
                    transform: "translateY(-50%)",
                    color: "var(--text-muted)", pointerEvents: "none",
                  }}
                />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  placeholder="you@example.com"
                  style={{ ...inputStyle, paddingLeft: 40 }}
                  onFocus={focusStyle}
                  onBlur={blurStyle}
                />
              </div>
            </div>

            <PasswordInput
              label="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              placeholder="Min 8 characters"
              style={{ background: "var(--bg-elevated)" }}
            />

            <PasswordInput
              label="Confirm password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              placeholder="Repeat your password"
              style={{ background: "var(--bg-elevated)" }}
            />

            <button type="submit" style={primaryBtnStyle}>
              Continue
              <ChevronRight size={16} />
            </button>

            <p style={{ textAlign: "center", fontSize: "0.875rem", color: "var(--text-secondary)", margin: "0.25rem 0 0" }}>
              Already have an account?{" "}
              <Link href="/login" style={{ color: "var(--accent)", fontWeight: 500, textDecoration: "none" }}>
                Sign in
              </Link>
            </p>
          </form>
        )}

        {/* ── Step 2 ── */}
        {step === 2 && (
          <form onSubmit={handleStep2} style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
            <div>
              <label style={labelStyle}>
                Username <span style={{ color: "var(--danger)" }}>*</span>
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value.replace(/\s/g, ""))}
                required
                placeholder="drjohnsmith"
                style={inputStyle}
                onFocus={focusStyle}
                onBlur={blurStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Full Name</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Dr. John Smith"
                style={inputStyle}
                onFocus={focusStyle}
                onBlur={blurStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Country</label>
              <input
                type="text"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                placeholder="India"
                style={inputStyle}
                onFocus={focusStyle}
                onBlur={blurStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Position</label>
              <select
                value={position}
                onChange={(e) => setPosition(e.target.value)}
                style={{ ...inputStyle, appearance: "auto" }}
              >
                <option value="">Select your position</option>
                {POSITIONS.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>

            <div>
              <label style={labelStyle}>Specialty</label>
              <div style={{ position: "relative" }}>
                <input
                  type="text"
                  value={specialtyInput}
                  onChange={(e) => {
                    setSpecialtyInput(e.target.value);
                    setSpecialty(e.target.value);
                    setShowSpecialtySuggestions(true);
                  }}
                  onFocus={() => setShowSpecialtySuggestions(true)}
                  onBlur={() => setTimeout(() => setShowSpecialtySuggestions(false), 150)}
                  placeholder="e.g. Cardiology"
                  style={inputStyle}
                />
                {showSpecialtySuggestions && specialtyInput && filteredSpecialties.length > 0 && (
                  <div
                    style={{
                      position: "absolute",
                      top: "100%",
                      left: 0,
                      right: 0,
                      background: "var(--bg-surface)",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius-md)",
                      boxShadow: "var(--shadow-md)",
                      zIndex: 10,
                      maxHeight: 180,
                      overflowY: "auto",
                      marginTop: 2,
                    }}
                  >
                    {filteredSpecialties.slice(0, 8).map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => {
                          setSpecialty(s);
                          setSpecialtyInput(s);
                          setShowSpecialtySuggestions(false);
                        }}
                        style={{
                          display: "block",
                          width: "100%",
                          padding: "8px 14px",
                          background: "transparent",
                          border: "none",
                          cursor: "pointer",
                          textAlign: "left",
                          fontSize: "0.875rem",
                          color: "var(--text-primary)",
                          transition: "background var(--transition)",
                        }}
                        onMouseOver={(e) => (e.currentTarget.style.background = "var(--bg-hover)")}
                        onMouseOut={(e) => (e.currentTarget.style.background = "transparent")}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div>
              <label style={labelStyle}>Institute / Hospital</label>
              <input
                type="text"
                value={institute}
                onChange={(e) => setInstitute(e.target.value)}
                placeholder="AIIMS New Delhi"
                style={inputStyle}
                onFocus={focusStyle}
                onBlur={blurStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Institution Type</label>
              <select
                value={institutionType}
                onChange={(e) => setInstitutionType(e.target.value)}
                style={{ ...inputStyle, appearance: "auto" }}
              >
                <option value="">Select type</option>
                {INSTITUTION_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>

            <label
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "0.5rem",
                cursor: "pointer",
                fontSize: "0.8rem",
                color: "var(--text-secondary)",
                userSelect: "none",
                marginTop: "0.25rem",
              }}
            >
              <input
                type="checkbox"
                checked={newsletter}
                onChange={(e) => setNewsletter(e.target.checked)}
                style={{ accentColor: "var(--accent)", marginTop: 2, flexShrink: 0 }}
              />
              Keep me updated on new features (optional)
            </label>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
              <button type="submit" style={primaryBtnStyle}>
                Continue
                <ChevronRight size={16} />
              </button>
              <button
                type="button"
                onClick={() => { setError(null); setStep(3); }}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "0.85rem",
                  color: "var(--text-muted)",
                  textDecoration: "underline",
                  padding: "4px 0",
                }}
              >
                Skip for now
              </button>
            </div>
          </form>
        )}

        {/* ── Step 3 ── */}
        {step === 3 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            <p
              style={{
                margin: 0,
                fontSize: "0.85rem",
                color: "var(--text-secondary)",
                lineHeight: 1.6,
                padding: "0.75rem 1rem",
                background: "var(--bg-elevated)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--border)",
              }}
            >
              Iatronix uses your own API key. Your key is encrypted and stored securely.
              We never use it for anything other than your queries.
            </p>

            {/* Tabs */}
            <div style={{ display: "flex", borderBottom: "1px solid var(--border)", gap: "1rem" }}>
              {(["anthropic", "openai"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveKeyTab(tab)}
                  style={{
                    padding: "8px 4px",
                    background: "none",
                    border: "none",
                    borderBottom: `2px solid ${activeKeyTab === tab ? "var(--accent)" : "transparent"}`,
                    marginBottom: -1,
                    cursor: "pointer",
                    fontWeight: activeKeyTab === tab ? 600 : 400,
                    color: activeKeyTab === tab ? "var(--text-primary)" : "var(--text-secondary)",
                    fontSize: "0.9rem",
                    transition: "all var(--transition)",
                    textTransform: "capitalize",
                  }}
                >
                  {tab === "anthropic" ? "Anthropic" : "OpenAI"}
                </button>
              ))}
            </div>

            {activeKeyTab === "anthropic" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <PasswordInput
                  label="Anthropic API Key"
                  value={anthropicKey}
                  onChange={(e) => setAnthropicKey(e.target.value)}
                  placeholder="sk-ant-api03-..."
                  style={{ background: "var(--bg-elevated)" }}
                />
                <a
                  href="https://console.anthropic.com/"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    fontSize: "0.825rem",
                    color: "var(--accent)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.35rem",
                    textDecoration: "none",
                  }}
                >
                  Get your API key
                  <ExternalLink size={13} />
                </a>
              </div>
            )}

            {activeKeyTab === "openai" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <PasswordInput
                  label="OpenAI API Key"
                  value={openaiKey}
                  onChange={(e) => setOpenaiKey(e.target.value)}
                  placeholder="sk-..."
                  style={{ background: "var(--bg-elevated)" }}
                />
                <a
                  href="https://platform.openai.com/api-keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    fontSize: "0.825rem",
                    color: "var(--accent)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.35rem",
                    textDecoration: "none",
                  }}
                >
                  Get your API key
                  <ExternalLink size={13} />
                </a>
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <button
                onClick={() => handleStep3(false)}
                disabled={loading}
                style={{ ...primaryBtnStyle, opacity: loading ? 0.6 : 1 }}
              >
                {loading ? "Creating account..." : "Save & Continue"}
              </button>
              <button
                onClick={() => handleStep3(true)}
                disabled={loading}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "0.85rem",
                  color: "var(--text-muted)",
                  textDecoration: "underline",
                  padding: "4px 0",
                }}
              >
                Skip for now
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Shared styles ──────────────────────────────────────────────────────────

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: "0.875rem",
  fontWeight: 500,
  color: "var(--text-secondary)",
  marginBottom: "0.375rem",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 14px",
  background: "var(--bg-elevated)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-md)",
  color: "var(--text-primary)",
  fontSize: "0.9rem",
  outline: "none",
  boxSizing: "border-box",
  transition: "border-color var(--transition), box-shadow var(--transition)",
};

const primaryBtnStyle: React.CSSProperties = {
  width: "100%",
  padding: "11px",
  background: "var(--accent)",
  border: "none",
  borderRadius: "var(--radius-md)",
  color: "#fff",
  fontSize: "0.95rem",
  fontWeight: 600,
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "0.4rem",
  transition: "background var(--transition), transform var(--transition)",
};

const focusStyle = (e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) => {
  e.currentTarget.style.borderColor = "var(--border-focus)";
  e.currentTarget.style.boxShadow = "0 0 0 3px var(--accent-glow)";
};
const blurStyle = (e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) => {
  e.currentTarget.style.borderColor = "var(--border)";
  e.currentTarget.style.boxShadow = "none";
};
