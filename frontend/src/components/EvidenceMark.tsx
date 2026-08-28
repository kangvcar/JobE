import type { EvidenceGrade } from "../api/types";
import { GRADE_LABEL } from "../api/labels";

export function EvidenceMark({
  grade,
  withLabel = true,
}: {
  grade: EvidenceGrade;
  withLabel?: boolean;
}) {
  const title = GRADE_LABEL[grade];
  return (
    <span className="inline-flex items-center gap-1.5 align-middle" title={title}>
      <span
        aria-hidden="true"
        className={[
          "inline-block size-2.5 shrink-0",
          grade === "multi_source" && "bg-accent",
          grade === "single_source" && "border border-ink bg-transparent",
          grade === "weak" && "border border-dotted border-ink-soft bg-transparent",
        ]
          .filter(Boolean)
          .join(" ")}
      />
      {withLabel ? (
        <span className="font-mono text-[11px] tracking-wide text-ink-soft">{title}</span>
      ) : (
        <span className="sr-only">{title}</span>
      )}
    </span>
  );
}
