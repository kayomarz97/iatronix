"use client";

import { SearchBar } from "@/components/ui/SearchBar";
import { ModelSelector } from "@/components/ui/ModelSelector";
import { useQuery } from "@/hooks/useQuery";

export default function HomePage() {
  const { submitQuery, isLoading } = useQuery();

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8">
      <div className="text-center space-y-3">
        <h1 className="text-4xl font-bold text-primary">Iatronix</h1>
        <p className="text-text-secondary text-lg max-w-xl">
          AI-powered medical reference with evidence grading. Query drugs,
          diseases, or compare treatments.
        </p>
      </div>

      <div className="w-full max-w-2xl space-y-4">
        <SearchBar onSubmit={submitQuery} isLoading={isLoading} />
        <div className="flex justify-center">
          <ModelSelector />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl w-full text-sm">
        <ExampleCard
          title="Drug Query"
          example="metformin dosing and interactions"
          onClick={() => submitQuery("metformin dosing and interactions")}
        />
        <ExampleCard
          title="Disease Query"
          example="heart failure management guidelines"
          onClick={() => submitQuery("heart failure management guidelines")}
        />
        <ExampleCard
          title="Comparison"
          example="lisinopril vs losartan for hypertension"
          onClick={() =>
            submitQuery("lisinopril vs losartan for hypertension")
          }
        />
      </div>
    </div>
  );
}

function ExampleCard({
  title,
  example,
  onClick,
}: {
  title: string;
  example: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="p-4 rounded-lg border border-border bg-surface-alt hover:bg-surface-hover transition-colors text-left cursor-pointer"
    >
      <div className="font-medium text-text mb-1">{title}</div>
      <div className="text-text-muted text-xs">{example}</div>
    </button>
  );
}
