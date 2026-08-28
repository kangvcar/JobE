import type { MatchTier } from "../api/types";
import { TIER_LABEL } from "../api/labels";

const ORDER: MatchTier[] = ["strong", "adequate", "gapped", "mismatch"];

export function MatchRail({ tier }: { tier: MatchTier }) {
  return (
    <div>
      <p className="font-sans text-3xl font-medium tracking-tight text-ink text-balance">{TIER_LABEL[tier]}</p>
      <ol className="mt-4 flex flex-wrap gap-x-6 gap-y-2" aria-label="匹配档位">
        {ORDER.map((t) => {
          const current = t === tier;
          return (
            <li key={t} className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className={
                  current
                    ? "size-2.5 bg-accent"
                    : "size-2.5 border border-ink-faint bg-transparent"
                }
              />
              <span className={current ? "text-sm text-ink" : "text-sm text-ink-faint"}>
                {TIER_LABEL[t]}
                {current ? <span className="sr-only">，当前档位</span> : null}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
