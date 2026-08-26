// Path: src/components/metric-card.tsx
// Description: Shared summary metric with consistent loading and emphasis states.

interface MetricCardProps {
    label: string;
    value: string | number;
    note: string;
    loading?: boolean;
    tone?: "default" | "accent" | "operational";
}

export default function MetricCard({ label, value, note, loading = false, tone = "default" }: MetricCardProps) {
    const toneClass = tone === "default" ? "" : ` metric-${tone}`;

    return (
        <article className={`metric-card${toneClass}`} aria-busy={loading}>
            <span>{label}</span>
            {loading ? <span className="metric-skeleton metric-skeleton-value" /> : <strong>{value}</strong>}
            {loading ? <span className="metric-skeleton metric-skeleton-note" /> : <small>{note}</small>}
        </article>
    );
}
