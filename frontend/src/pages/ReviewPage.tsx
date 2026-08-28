import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { REVIEW_KIND_LABEL, VERDICT_LABEL } from "../api/labels";
import type { ReviewItem } from "../api/types";
import { formatTime } from "../lib/format";

export function ReviewPage() {
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, setParams] = useSearchParams();

  useEffect(() => {
    api
      .getReviewQueue()
      .then(setItems)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "队列加载失败"));
  }, []);

  async function decide(id: string, decision: "confirm" | "reject") {
    const next = await api.decideReview(id, decision);
    setItems(next);
  }

  return (
    <main id="main" className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-3xl font-medium tracking-tight">待确认</h1>
      <p className="mt-3 max-w-[55ch] text-pretty text-ink-soft">
        只有四类动作需要人点头：新兴岗位首次发布、核心必备技能被删除、统计信号与 AI 审核结论矛盾、用户举报后的处置。不是一套审批流。
      </p>
      {error ? (
        <p className="mt-6" role="alert">
          {error}。刷新页面重新取队列。
        </p>
      ) : null}
      {items && items.length === 0 ? (
        <p className="mt-10 text-ink-soft">没有需要人工拦截的事项。高影响动作出现时会排在这里。</p>
      ) : null}
      <ul className="mt-10 space-y-10">
        {(items ?? []).map((item) => (
          <li key={item.id}>
            <p className="font-mono text-xs text-ink-faint">
              {REVIEW_KIND_LABEL[item.kind]} · {formatTime(item.created_at)}
            </p>
            <h2 className="mt-2 text-lg font-medium">{item.title}</h2>
            <p className="mt-2 text-pretty text-ink-soft">{item.body}</p>
            {item.ai_verdict ? (
              <p className="mt-2 text-sm">AI 审核员：{VERDICT_LABEL[item.ai_verdict]}</p>
            ) : (
              <p className="mt-2 text-sm text-ink-soft">这条没有自动审核结论，需要人直接判断。</p>
            )}
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                className="rounded-[4px] bg-accent px-3 py-2 text-sm text-accent-fg"
                onClick={() => decide(item.id, "confirm")}
              >
                确认发布
              </button>
              <button
                type="button"
                className="rounded-[4px] border border-rule px-3 py-2 text-sm"
                onClick={() => decide(item.id, "reject")}
              >
                驳回
              </button>
              {item.evidence_ids[0] ? (
                <button
                  type="button"
                  className="px-3 py-2 text-sm text-accent"
                  onClick={() => {
                    const next = new URLSearchParams(window.location.search);
                    next.set("evidence", item.evidence_ids[0]);
                    setParams(next);
                  }}
                >
                  打开证据
                </button>
              ) : null}
              {item.role_id ? (
                <Link to={`/graph?node=${item.role_id}`} className="px-3 py-2 text-sm hover:underline">
                  查看岗位
                </Link>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
