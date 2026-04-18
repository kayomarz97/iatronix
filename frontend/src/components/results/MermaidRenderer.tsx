import dynamic from "next/dynamic";

const MermaidClient = dynamic(() => import("./MermaidClient").then((m) => ({ default: m.MermaidClient })), {
  ssr: false,
});

export function MermaidRenderer({ chart }: { chart: string }) {
  return <MermaidClient chart={chart} />;
}
