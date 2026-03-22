"use client";

import ReactMarkdown from "react-markdown";
import type { EvidenceResponse, StudyEvidence } from "@/lib/types";
import { ClaimItem } from "@/components/results/ClaimItem";
import { Accordion } from "@/components/ui/Accordion";
import { Badge } from "@/components/ui/Badge";
import { ReferenceList } from "@/components/results/ReferenceList";

interface EvidenceResultProps {
  data: EvidenceResponse;
}

function StudyRow({ study }: { study: StudyEvidence }) {
  const pmidUrl = study.pmid
    ? `https://pubmed.ncbi.nlm.nih.gov/${study.pmid}`
    : null;

  return (
    <div className="p-3 rounded-md bg-surface-alt border border-border text-sm">
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
    </div>
  );
}

export function EvidenceResult({ data }: EvidenceResultProps) {
  return (
    <div className="space-y-5">
      <div className="border-b border-border pb-4">
        <h2 className="text-2xl font-bold">{data.query_topic}</h2>
      </div>

      <div className="prose prose-sm max-w-none dark:prose-invert">
        <ReactMarkdown>{data.summary}</ReactMarkdown>
      </div>

      {data.supporting_studies.length > 0 && (
        <Accordion
          title="Supporting Studies"
          count={data.supporting_studies.length}
          defaultOpen
        >
          <div className="space-y-2">
            {data.supporting_studies.map((s, i) => (
              <StudyRow key={i} study={s} />
            ))}
          </div>
        </Accordion>
      )}

      {data.opposing_studies.length > 0 && (
        <Accordion
          title="Opposing / Contradictory Studies"
          count={data.opposing_studies.length}
        >
          <div className="space-y-2">
            {data.opposing_studies.map((s, i) => (
              <StudyRow key={i} study={s} />
            ))}
          </div>
        </Accordion>
      )}

      {data.clinical_recommendation && (
        <div>
          <h3 className="text-base font-semibold mb-2">
            Clinical Recommendation
          </h3>
          <ClaimItem claim={data.clinical_recommendation} />
        </div>
      )}

      <div className="p-3 rounded-md bg-surface-alt border border-border text-sm">
        <span className="font-medium">Guideline Status:</span>{" "}
        {data.guideline_status}
      </div>

      {data.references.length > 0 && (
        <ReferenceList references={data.references} />
      )}
    </div>
  );
}
