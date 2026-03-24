export function Footer() {
  return (
    <footer
      style={{
        borderTop: "1px solid var(--border)",
        padding: "1rem 1.25rem",
        textAlign: "center",
      }}
    >
      <p
        style={{
          margin: 0,
          fontSize: "0.75rem",
          color: "var(--text-muted)",
        }}
      >
        Iatronix Medical Reference — For clinical decision support only. Not a
        substitute for professional medical judgment.
      </p>
    </footer>
  );
}
