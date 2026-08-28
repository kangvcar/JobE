import { GAP_LABEL } from "../api/labels";
import type { Gap, GapKind } from "../api/types";
import { skillLevelWord } from "../lib/format";

const KINDS: GapKind[] = ["missing", "insufficient", "surplus"];

export function GapBoard({
  gaps,
  names,
  onSkill,
}: {
  gaps: Gap[];
  names: Record<string, string>;
  onSkill: (skillId: string) => void;
}) {
  return (
    <div className="grid gap-10 md:grid-cols-12">
      {KINDS.map((kind) => {
        const items = gaps.filter((g) => g.kind === kind);
        const span = kind === "missing" ? "md:col-span-6" : "md:col-span-3";
        return (
          <section key={kind} className={span}>
            <h3 className="text-sm text-ink-soft">
              {GAP_LABEL[kind]}
              <span className="ml-2 font-mono tabular text-ink">{items.length}</span>
            </h3>
            {items.length === 0 ? (
              <p className="mt-3 text-sm text-ink-faint">这一类是空的。</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {items.map((g) => (
                  <li key={`${g.kind}-${g.skill_id}`}>
                    <button
                      type="button"
                      onClick={() => onSkill(g.skill_id)}
                      className="w-full rounded-[4px] px-1 py-1 text-left text-sm text-ink hover:bg-paper-2"
                    >
                      <span className="block">{names[g.skill_id] ?? g.skill_id}</span>
                      <span className="block text-xs text-ink-soft">
                        {kind === "surplus"
                          ? "目标岗位并不要求"
                          : kind === "insufficient"
                            ? `当前：${skillLevelWord(g.held_level)}`
                            : "技能画像里没有这个技能点"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
