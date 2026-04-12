"use client";

import ReactMarkdown from "react-markdown";
import type { EvidenceResponse, StudyEvidence } from "@/lib/types";
import { ClaimItem } from "@/components/results/ClaimItem";
import { Badge } from "@/components/ui/Badge";
import { ReferenceList } from "@/components/results/ReferenceList";
import { ResultHero, ResultMetaCard, ResultSection } from "@/components/results/ResultChrome";

interface EvidenceResultProps {
  data: EvidenceResponse;
}

function StudyRow({ study }: { study: StudyEvidence }) {
  const pmidUrl = study.pmid
    ? `https://pubmed.ncbi.nlm.nih.gov/${study.pmid}`
    : null;

  return (
    <ResultMetaCard className="text-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="font-medium">
          {pmidUrl ? (
            <a
              href={pmidUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline"
            >
              {study.title}
            </a>
          ) : (
            study.title
          )}
        </div>
        <Badge>{`LOE ${study.loe}`}</Badge>
      </div>
      <p className="text-text-secondary mt-1">{study.finding}</p>
      <div className="flex gap-3 mt-2 text-xs text-text-muted">
        {study.year && <span>{study.year}</span>}
        {study.sample_size && <span>n={study.sample_size}</span>}
        {study.pmid && <span>PMID: {study.pmid}</span>}
      </div>
    </ResultMetaCard>
  );
}

export function EvidenceResult({ data }: EvidenceResultProps) {
  const directAnswer =
    data.clinical_recommendation?.value ?? firstSentence(data.summary) ?? data.summary;

  return (
    <div className="space-y-6">
      <ResultHero
        eyebrow="Evidence Review"
        title={data.query_topic}
        subtitle={data.guideline_status}
        stats={[
          { label: "supporting studies", value: data.supporting_studies?.length ?? 0 },
          { label: "opposing studies", value: data.opposing_studies?.length ?? 0 },
          { label: "references", value: data.references?.length ?? 0 },
        ]}
        directAnswer={directAnswer}
      />

      <ResultSection title="Evidence Summary" eyebrow="What the literature shows">
        <div className="prose prose-sm max-w-none dark:prose-invert">
          <ReactMarkdown>{data.summary}</ReactMarkdown>
        </div>
      </ResultSection>

      {data.supporting_studies?.length > 0 && (
        <ResultSection title="Supporting Studies" eyebrow="Favors use">
          <div className="space-y-2">
            {data.supporting_studies.map((s, i) => (
              <StudyRow key={i} study={s} />
            ))}
          </div>
        </ResultSection>
      )}

      {data.opposing_studies?.length > 0 && (
        <ResultSection title="Opposing or Contradictory Studies" eyebrow="Counters or limits use">
          <div className="space-y-2">
            {data.opposing_studies.map((s, i) => (
              <StudyRow key={i} study={s} />
            ))}
          </div>
        </ResultSection>
      )}

      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        {data.clinical_recommendation && (
          <ResultSection title="Clinical Recommendation" eyebrow="Practical bottom line">
            <ClaimItem claim={data.clinical_recommendation} />
          </ResultSection>
        )}

        <ResultSection title="Guideline Status" eyebrow="Formal positioning">
          <p className="text-sm leading-7 text-text-secondary">
            {data.guideline_status}
          </p>
        </ResultSection>
      </div>

      {data.references?.length > 0 && <ReferenceList references={data.references} />}
    </div>
  );
}

function firstSentence(text: string): string | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  const match = trimmed.match(/.+?[.!?](\s|$)/);
  return (match?.[0] ?? trimmed).trim();
}
