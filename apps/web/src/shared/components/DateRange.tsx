interface Props {
  start: string;
  end: string;
  onChange: (start: string, end: string) => void;
}

export function DateRange({ start, end, onChange }: Props) {
  return (
    <div className="date-range" aria-label="조회 기간">
      <label>시작<input type="date" value={start} max={end} onChange={(event) => onChange(event.target.value, end)} /></label>
      <span>~</span>
      <label>종료<input type="date" value={end} min={start} onChange={(event) => onChange(start, event.target.value)} /></label>
    </div>
  );
}
