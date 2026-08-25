// Path: src/lib/format.ts
// Description: Shared display formatting helpers for the admin dashboard.

import type { DimensionScore } from "./models";

export function formatDate(value: string): string {
    return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(new Date(value));
}

export function initials(email: string | null): string {
    if (!email) return "?";
    const localPart = email.split("@")[0] || "?";
    return localPart
        .split(/[._-]/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase())
        .join("");
}

export function formatGate(value: string | null | undefined): string {
    if (!value) return "Not scored";
    return value
        .toLowerCase()
        .split("_")
        .filter(Boolean)
        .map((part) => part[0]?.toUpperCase() + part.slice(1))
        .join(" ");
}

export function dimensionLabel(dimensions: DimensionScore[], key: string): string {
    return dimensions.find((dimension) => dimension.dimension === key)?.dimension_label || key;
}
