import { Eye, FileJson2, LoaderCircle, X } from "lucide-react";
import { useState } from "react";
import { createPortal } from "react-dom";

import { getJson, query } from "../../shared/api/client";
import type { ScheduledArtifactContent } from "./types";

interface ScheduledArtifactViewerProps {
  artifact: { label: string; path: string };
}

export function ScheduledArtifactViewer({ artifact }: ScheduledArtifactViewerProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [content, setContent] = useState<ScheduledArtifactContent | null>(null);

  async function showArtifact() {
    setOpen(true);
    if (content || loading) return;
    setLoading(true);
    setError(null);
    try {
      setContent(await getJson<ScheduledArtifactContent>(query(
        "/api/v1/runtime/scheduled-artifact",
        { path: artifact.path },
      )));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "파일을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return <>
    <button className="icon-button" type="button" title={`${artifact.label} 열기`} onClick={() => void showArtifact()}>
      <Eye size={14} />
    </button>
    {open && createPortal(
      <div className="artifact-viewer-backdrop" role="presentation" onMouseDown={() => setOpen(false)}>
        <section className="artifact-viewer" role="dialog" aria-modal="true" aria-label={`${artifact.label} 원본 파일`} onMouseDown={(event) => event.stopPropagation()}>
          <header>
            <FileJson2 size={18} />
            <div><strong>{artifact.label}</strong><span>{artifact.path}</span></div>
            <button className="icon-button" type="button" title="닫기" onClick={() => setOpen(false)}><X size={16} /></button>
          </header>
          <div className="artifact-viewer-content">
            {loading && <div className="artifact-viewer-state"><LoaderCircle className="spin" size={18} />불러오는 중</div>}
            {error && <div className="artifact-viewer-state data-state-error">{error}</div>}
            {content && <pre>{content.format === "json"
              ? JSON.stringify(content.json_content, null, 2)
              : content.text_content}</pre>}
          </div>
        </section>
      </div>,
      document.body,
    )}
  </>;
}
