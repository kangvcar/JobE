import * as Dialog from "@radix-ui/react-dialog";
import { X } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { GRADE_LABEL } from "../api/labels";
import type { EvidenceDetail } from "../api/types";
import { formatTime } from "../lib/format";
import { EvidenceMark } from "./EvidenceMark";

export function EvidenceDrawer() {
  const [params, setParams] = useSearchParams();
  const id = params.get("evidence");
  const [data, setData] = useState<EvidenceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) {
      setData(null);
      setError(null);
      return;
    }
    let alive = true;
    setData(null);
    setError(null);
    api
      .getEvidence(id)
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : "证据加载失败");
      });
    return () => {
      alive = false;
    };
  }, [id]);

  function close() {
    const next = new URLSearchParams(params);
    next.delete("evidence");
    setParams(next, { replace: true });
  }

  return (
    <Dialog.Root open={Boolean(id)} onOpenChange={(open) => !open && close()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[40] bg-ink/35" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 right-0 z-[50] flex h-[100dvh] w-full max-w-xl flex-col overflow-auto bg-paper p-6 shadow-[0_0_0_1px_var(--color-rule)] focus:outline-none"
        >
          <div className="flex items-start justify-between gap-4">
            <Dialog.Title className="text-xl font-medium tracking-tight">证据</Dialog.Title>
            <Dialog.Close
              className="inline-flex size-10 items-center justify-center rounded-[4px] hover:bg-paper-2"
              aria-label="关闭证据"
            >
              <X size={18} weight="bold" />
            </Dialog.Close>
          </div>
          {error ? (
            <p className="mt-6 text-sm text-ink" role="alert">
              {error}。检查地址里的证据编号，或回到技能点重新打开。
            </p>
          ) : !data ? (
            <p className="mt-6 text-sm text-ink-soft">正在取原文片段。</p>
          ) : (
            <EvidenceBody data={data} />
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function EvidenceBody({ data }: { data: EvidenceDetail }) {
  return (
    <div className="mt-6">
      <EvidenceMark grade={data.confidence >= 0.8 ? "multi_source" : data.confidence >= 0.55 ? "single_source" : "weak"} />
      <p className="mt-4 max-w-[52ch] text-pretty text-base leading-relaxed">「{data.quote}」</p>
      <dl className="mt-6 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-ink-soft">来源</dt>
        <dd>{data.source_name}</dd>
        <dt className="text-ink-soft">采集时间</dt>
        <dd className="font-mono tabular">{formatTime(data.fetched_at)}</dd>
        <dt className="text-ink-soft">证据等级</dt>
        <dd>
          {GRADE_LABEL[data.confidence >= 0.8 ? "multi_source" : data.confidence >= 0.55 ? "single_source" : "weak"]}
        </dd>
      </dl>
      <h3 className="mt-8 text-sm text-ink-soft">在原始文档上的位置</h3>
      {data.document.kind === "resume" ? (
        <ResumeHighlight doc={data} />
      ) : (
        <PostingHighlight doc={data} />
      )}
    </div>
  );
}

function ResumeHighlight({ doc }: { doc: EvidenceDetail }) {
  const page = doc.document.pages[doc.span.page_index ?? 0];
  const box = doc.span.bbox;
  return (
    <div className="mt-3 border border-rule bg-paper-2 p-3">
      <p className="font-mono text-xs text-ink-soft">{doc.document.title} · 第 {(doc.span.page_index ?? 0) + 1} 页</p>
      <div className="relative mt-3 aspect-[210/297] w-full bg-paper">
        {page?.lines.map((line) => (
          <p
            key={`${line.y}-${line.text}`}
            className="absolute text-[10px] leading-tight text-ink sm:text-xs"
            style={{ left: `${line.x * 100}%`, top: `${line.y * 100}%`, width: `${line.width * 100}%` }}
          >
            {line.text}
          </p>
        ))}
        {box ? (
          <div
            className="pointer-events-none absolute border-2 border-accent bg-accent/15"
            style={{
              left: `${box[0] * 100}%`,
              top: `${box[1] * 100}%`,
              width: `${(box[2] - box[0]) * 100}%`,
              height: `${(box[3] - box[1]) * 100}%`,
            }}
            aria-label="证据在简历页上的定位框"
          />
        ) : null}
      </div>
    </div>
  );
}

function PostingHighlight({ doc }: { doc: EvidenceDetail }) {
  const text = doc.document.text;
  const start = Math.max(0, doc.span.start);
  const end = Math.min(text.length, Math.max(start, doc.span.end));
  const before = text.slice(0, start);
  const hit = text.slice(start, end) || doc.quote;
  const after = text.slice(end);
  return (
    <div className="mt-3 border border-rule bg-paper-2 p-4">
      <p className="font-mono text-xs text-ink-soft">{doc.document.title}</p>
      <p className="mt-3 max-w-[60ch] text-sm leading-relaxed text-pretty">
        {before}
        <mark className="bg-accent/25 text-ink">{hit}</mark>
        {after}
      </p>
    </div>
  );
}
