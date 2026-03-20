interface CardProps {
  children: React.ReactNode;
  className?: string;
  variant?: "default" | "degraded";
}

export function Card({
  children,
  className = "",
  variant = "default",
}: CardProps) {
  const variants = {
    default: "bg-surface border-border",
    degraded: "bg-surface-alt border-border opacity-75",
  };

  return (
    <div
      className={`rounded-lg border p-4 ${variants[variant]} ${className}`}
    >
      {children}
    </div>
  );
}
