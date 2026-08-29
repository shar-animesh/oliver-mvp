// Path: src/api.ts
// Description: Typed HTTP client for the admin backend.

import type {
    AssessmentTestInput,
    AssessmentTestResult,
    EmailThreadDetail,
    EmailThreadSummary,
    InitiativeSummary,
    InitiativeDetail,
    IntelligenceOverview,
} from "./lib/models";

const ADMIN_API_ROOT = (import.meta.env.VITE_ADMIN_API_URL || "/api").replace(/\/$/, "");
const API_V1 = `${ADMIN_API_ROOT}/v1`;

export interface AdminSession {
    username: string;
    roles: string[];
}

let accessTokenProvider: (() => Promise<string | null>) | null = null;

export function configureAccessTokenProvider(provider: () => Promise<string | null>): void {
    accessTokenProvider = provider;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const accessToken = accessTokenProvider ? await accessTokenProvider() : null;
    const response = await fetch(`${API_V1}${path}`, {
        credentials: "include",
        ...init,
        headers: {
            ...(init?.body ? { "Content-Type": "application/json" } : {}),
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
            ...init?.headers,
        },
    });
    if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail || `Request failed (${response.status})`);
    }
    return (response.status === 204 ? undefined : await response.json()) as T;
}

export const api = {
    getSession: (): Promise<AdminSession> => request<AdminSession>("/auth/me"),
    login: (username: string, password: string): Promise<AdminSession> =>
        request<AdminSession>("/auth/login", {
            method: "POST",
            body: JSON.stringify({ username, password }),
        }),
    logout: (): Promise<void> => request<void>("/auth/logout", { method: "POST" }),
    listInitiatives: (): Promise<InitiativeSummary[]> => request<InitiativeSummary[]>("/initiatives"),
    getInitiative: (id: string): Promise<InitiativeDetail> => request<InitiativeDetail>(`/initiatives/${id}`),
    getIntelligence: (): Promise<IntelligenceOverview> => request<IntelligenceOverview>("/intelligence"),
    listEmailThreads: (): Promise<EmailThreadSummary[]> => request<EmailThreadSummary[]>("/email-threads"),
    getEmailThread: (id: string): Promise<EmailThreadDetail> => request<EmailThreadDetail>(`/email-threads/${id}`),
    runAssessmentTest: (input: AssessmentTestInput): Promise<AssessmentTestResult> =>
        request<AssessmentTestResult>("/commands/assessment-test", {
            method: "POST",
            body: JSON.stringify(input),
        }),
};
