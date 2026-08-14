import type { ReactNode } from "react";

interface Props {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Panel({ title, meta, children, className = "" }: Props) {
  return (
    <section className={`panel ${className}`.trim()}>
      <div className="panel-heading">
        <h2>{title}</h2>
        {meta && <div className="panel-meta">{meta}</div>}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}
