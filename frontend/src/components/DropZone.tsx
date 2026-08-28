import { useId, useRef, type DragEvent, type KeyboardEvent } from "react";

export function DropZone({
  onFile,
  busy,
}: {
  onFile: (file: File) => void;
  busy?: boolean;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  function take(file: File | undefined) {
    if (!file || busy) return;
    onFile(file);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    take(e.dataTransfer.files[0]);
  }

  function onKey(e: KeyboardEvent<HTMLLabelElement>) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      inputRef.current?.click();
    }
  }

  return (
    <label
      htmlFor={inputId}
      tabIndex={0}
      onKeyDown={onKey}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
      className="block cursor-pointer border border-dashed border-ink/40 bg-paper-2 px-5 py-8 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
    >
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only opacity-0"
        disabled={busy}
        onChange={(e) => take(e.target.files?.[0])}
      />
      <p className="text-lg font-medium text-ink">把简历拖到这里</p>
      <p className="mt-2 max-w-[42ch] text-pretty text-sm text-ink-soft">
        {busy
          ? "正在抽取技能点。版面坐标由字符串匹配回填，不会让模型瞎标位置。"
          : "PDF 即可，游客也能用，不用登录。解析后会生成技能画像，并和当前目标岗位对比。"}
      </p>
    </label>
  );
}
