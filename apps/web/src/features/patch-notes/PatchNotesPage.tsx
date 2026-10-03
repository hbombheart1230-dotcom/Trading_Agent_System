import { BookOpenText, CalendarDays, Filter, Search, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { PageHeader } from "../../shared/components/PageHeader";
import { StatusPill } from "../../shared/components/StatusPill";
import { provenanceRows } from "./provenance";
import type { PatchNoteEntry, PatchNotesResponse } from "./types";

const ALL = "ALL";

function includesQuery(entry: PatchNoteEntry, query: string): boolean {
  if (!query) return true;
  const text = [
    entry.date, entry.version, entry.title, entry.stage, entry.summary, entry.impact,
    ...entry.types, ...entry.details,
    ...provenanceRows(entry.provenance).flatMap((row) => [row.label, row.value]),
  ].join(" ").toLocaleLowerCase();
  return text.includes(query.toLocaleLowerCase());
}

export function PatchNotesPage() {
  const notes = useApi<PatchNotesResponse>("/api/v1/patch-notes");
  const [query, setQuery] = useState("");
  const [stage, setStage] = useState(ALL);
  const [type, setType] = useState(ALL);
  const filtered = useMemo(
    () => (notes.data?.entries ?? []).filter((entry) => (
      (stage === ALL || entry.stage === stage)
      && (type === ALL || entry.types.includes(type))
      && includesQuery(entry, query.trim())
    )),
    [notes.data, query, stage, type],
  );
  const latest = notes.data?.entries[0];

  return (
    <>
      <PageHeader
        title="패치 노트"
        description="시스템의 주요 변경과 운영 영향을 날짜순으로 확인합니다. 기존 이력은 보존하고 핵심 변경만 누적합니다."
        actions={notes.data && <><StatusPill status={notes.data.status} /><span className="readonly-flag">READ ONLY</span></>}
      />
      <div className="patch-note-metrics">
        <div><span>전체 변경</span><strong>{notes.data?.entry_count ?? 0}</strong><small>누적 항목</small></div>
        <div><span>최신 기준</span><strong>{latest?.date ?? "-"}</strong><small>{latest?.version ?? "기록 없음"}</small></div>
        <div><span>개발 단계</span><strong>{notes.data?.stages.length ?? 0}</strong><small>분류된 stage</small></div>
        <div><span>변경 유형</span><strong>{notes.data?.types.length ?? 0}</strong><small>검색 가능한 tag</small></div>
      </div>
      <section className="patch-note-toolbar" aria-label="패치 노트 필터">
        <label className="patch-note-search">
          <Search size={15} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="제목, 내용, 태그 검색" aria-label="패치 노트 검색" />
        </label>
        <label className="patch-note-filter">
          <Filter size={14} />
          <select value={stage} onChange={(event) => setStage(event.target.value)} aria-label="개발 단계 필터">
            <option value={ALL}>전체 단계</option>
            {notes.data?.stages.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <select className="filter-select" value={type} onChange={(event) => setType(event.target.value)} aria-label="변경 유형 필터">
          <option value={ALL}>전체 유형</option>
          {notes.data?.types.map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
        <span className="patch-note-result">{filtered.length}개 표시</span>
      </section>
      <DataState loading={notes.loading} error={notes.error} empty={!filtered.length} emptyText="조건에 맞는 패치 노트가 없습니다." onRetry={notes.refresh}>
        <div className="patch-note-timeline">
          {filtered.map((entry, index) => (
            <article className="patch-note-entry" key={`${entry.date}-${entry.version}-${entry.title}`}>
              <div className="patch-note-marker" aria-hidden="true"><span /></div>
              <details open={index === 0 && !query && stage === ALL && type === ALL}>
                <summary>
                  <div className="patch-note-meta">
                    <span><CalendarDays size={13} />{entry.date}</span>
                    <span>{entry.stage}</span>
                    {entry.status === "current" && <b>CURRENT</b>}
                  </div>
                  <h2>{entry.title}</h2>
                  <p>{entry.summary}</p>
                  <div className="tag-list">{entry.types.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div>
                </summary>
                <div className="patch-note-body">
                  {entry.provenance && provenanceRows(entry.provenance).length > 0 && (
                    <section className="patch-note-provenance">
                      <h3><ShieldCheck size={14} />Development Provenance</h3>
                      <dl>
                        {provenanceRows(entry.provenance).map((row) => (
                          <div key={row.label}>
                            <dt>{row.label}</dt>
                            <dd className={row.mono ? "mono" : undefined}>{row.value}</dd>
                          </div>
                        ))}
                      </dl>
                    </section>
                  )}
                  <section><h3>변경 내용</h3><ul>{entry.details.map((detail) => <li key={detail}>{detail}</li>)}</ul></section>
                  <section className="patch-note-impact"><h3>운영 영향</h3><p>{entry.impact}</p></section>
                  <section><h3><BookOpenText size={14} />근거 문서</h3><ul className="patch-note-sources">{entry.sources.map((source) => <li className="mono" key={source}>{source}</li>)}</ul></section>
                </div>
              </details>
            </article>
          ))}
        </div>
      </DataState>
    </>
  );
}
