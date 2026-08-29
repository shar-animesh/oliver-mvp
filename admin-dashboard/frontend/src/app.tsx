// Path: src/app.tsx
// Description: Authenticated shell for the Oliver administration dashboard.

import { useEffect, useState, type FormEvent } from "react";

import { api, configureAccessTokenProvider, type AdminSession } from "./api";
import { authMode, getAccessToken, initializeAuthentication, signInWithEntra, signOutFromEntra } from "./auth";
import AssessmentLab from "./pages/assessment-lab";
import EmailThreads from "./pages/email-threads";
import InitiativeDetail from "./pages/initiative-detail";
import Initiatives from "./pages/initiatives";

type Workspace = "portfolio" | "conversations" | "assessment";

const workspaceDetails: Record<Workspace, { eyebrow: string; title: string }> = {
    portfolio: { eyebrow: "Portfolio", title: "Initiative lifecycle" },
    conversations: { eyebrow: "Operations", title: "Conversations and assessments" },
    assessment: { eyebrow: "Quality assurance", title: "Assessment laboratory" },
};

function workspaceFromLocation(): Workspace {
    const candidate = new URLSearchParams(window.location.search).get("workspace");
    return candidate === "conversations" || candidate === "assessment" ? candidate : "portfolio";
}

function queryValue(name: string): string | null {
    return new URLSearchParams(window.location.search).get(name);
}

function identityInitials(username: string): string {
    const name = username.split("@")[0] || username;
    return name
        .split(/[._\-\s]+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase())
        .join("");
}

function GridIcon() {
    return (
        <svg aria-hidden="true" viewBox="0 0 20 20">
            <path d="M3 3h5v5H3V3Zm9 0h5v5h-5V3ZM3 12h5v5H3v-5Zm9 0h5v5h-5v-5Z" />
        </svg>
    );
}

function InboxIcon() {
    return (
        <svg aria-hidden="true" viewBox="0 0 20 20">
            <path d="M3.5 4.5h13v10.75H13l-1.5 1.5h-3l-1.5-1.5H3.5V4.5Zm1.5 1.5v7.75h2.62l1.5 1.5h1.76l1.5-1.5H15V6H5Z" />
        </svg>
    );
}

function LabIcon() {
    return (
        <svg aria-hidden="true" viewBox="0 0 20 20">
            <path d="M7 2.5h6V4h-1v3.15l3.76 6.27A2.67 2.67 0 0 1 13.47 17H6.53a2.67 2.67 0 0 1-2.29-3.58L8 7.15V4H7V2.5Zm2.5 5.07-3.97 6.62a1.17 1.17 0 0 0 1 1.76h6.94a1.17 1.17 0 0 0 1-1.76L10.5 7.57V4h-1v3.57Zm-2.12 5.18h5.24l.9 1.5H6.48l.9-1.5Z" />
        </svg>
    );
}

function SignIn({ onAuthenticated }: { onAuthenticated: (session: AdminSession) => void }) {
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);

    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setSubmitting(true);
        setError(null);
        try {
            onAuthenticated(await api.login(username, password));
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : "Sign-in failed");
        } finally {
            setSubmitting(false);
        }
    }

    async function enterpriseSignIn() {
        setSubmitting(true);
        setError(null);
        try {
            await signInWithEntra();
            onAuthenticated(await api.getSession());
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : "Microsoft sign-in failed");
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <main className="signin-page">
            <div className="signin-layout">
                <section className="signin-story" aria-label="Oliver overview">
                    <div className="signin-brand">
                        <img
                            className="signin-logo"
                            src="https://www.siemens-energy.com/content/dam/siemensenergy-aem/images/logo/SE_Logo_White.png"
                            alt="Siemens Energy"
                        />
                        <span className="brand-divider" aria-hidden="true" />
                        <span className="oliver-wordmark">Oliver<small>Initiative operations</small></span>
                    </div>
                    <div className="signin-story-copy">
                        <p className="eyebrow">Siemens Energy / internal workspace</p>
                        <h1>Move every idea forward with confidence.</h1>
                        <p>One calm view of pilots, evidence, assessments and the decisions that keep innovation moving.</p>
                    </div>
                    <div className="signin-story-footer">
                        <span className="secure-indicator"><i /> Secure administrator access</span>
                        <span>Oliver v1.0</span>
                    </div>
                </section>
                <section className="signin-panel" aria-labelledby="signin-title">
                <img
                    className="signin-logo"
                    src="https://www.siemens-energy.com/content/dam/siemensenergy-aem/images/logo/SE_Logo_White.png"
                    alt="Siemens Energy"
                />
                <p className="eyebrow">Oliver administration</p>
                <h1 id="signin-title">Welcome back</h1>
                <p className="signin-intro">Sign in to review pilot progress, assessments and governed actions.</p>
                {authMode === "entra" ? (
                    <div className="enterprise-signin">
                        {error ? <p className="signin-error">{error}</p> : null}
                        <button type="button" onClick={() => void enterpriseSignIn()} disabled={submitting}>
                            {submitting ? "Opening Microsoft sign-in..." : "Continue with Microsoft"}
                        </button>
                    </div>
                ) : (
                    <form onSubmit={submit}>
                        <label htmlFor="username">Username</label>
                        <input
                            id="username"
                            autoComplete="username"
                            value={username}
                            onChange={(event) => setUsername(event.target.value)}
                            required
                        />
                        <label htmlFor="password">Password</label>
                        <input
                            id="password"
                            type="password"
                            autoComplete="current-password"
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                            required
                        />
                        {error ? <p className="signin-error">{error}</p> : null}
                        <button type="submit" disabled={submitting}>
                            {submitting ? "Signing in…" : "Sign in"}
                        </button>
                    </form>
                )}
                <div className="signin-meta">
                    <span className="secure-indicator"><i /> Encrypted session</span>
                    <small>{authMode === "entra" ? "Access is governed by Microsoft Entra app roles." : "Local development authentication only."}</small>
                </div>
            </section>
            </div>
        </main>
    );
}

function Dashboard({ session, onSignedOut }: { session: AdminSession; onSignedOut: () => void }) {
    const [workspace, setWorkspace] = useState<Workspace>(workspaceFromLocation);
    const [initiativeId, setInitiativeId] = useState<string | null>(() => queryValue("initiative"));
    const [threadId, setThreadId] = useState<string | null>(() => queryValue("thread"));
    const [signOutError, setSignOutError] = useState<string | null>(null);
    const canTestAssessment = session.roles.some((role) => role === "Oliver.Assessment.Test" || role === "Oliver.Platform.Admin");

    useEffect(() => {
        const syncWorkspace = () => {
            setWorkspace(workspaceFromLocation());
            setInitiativeId(queryValue("initiative"));
            setThreadId(queryValue("thread"));
        };
        window.addEventListener("popstate", syncWorkspace);
        return () => window.removeEventListener("popstate", syncWorkspace);
    }, []);

    function openWorkspace(nextWorkspace: Workspace, options: { initiativeId?: string; threadId?: string } = {}): void {
        const url = new URL(window.location.href);
        url.searchParams.set("workspace", nextWorkspace);
        if (options.initiativeId) url.searchParams.set("initiative", options.initiativeId);
        else url.searchParams.delete("initiative");
        if (options.threadId) url.searchParams.set("thread", options.threadId);
        else url.searchParams.delete("thread");
        window.history.pushState(null, "", url);
        setWorkspace(nextWorkspace);
        setInitiativeId(options.initiativeId || null);
        setThreadId(options.threadId || null);
    }

    function openInitiative(id: string): void {
        openWorkspace("portfolio", { initiativeId: id });
    }

    function openThread(id: string): void {
        openWorkspace("conversations", { threadId: id });
    }

    async function signOut() {
        setSignOutError(null);
        try {
            if (authMode === "entra") await signOutFromEntra();
            else await api.logout();
            onSignedOut();
        } catch (reason) {
            setSignOutError(reason instanceof Error ? reason.message : "Sign-out failed");
        }
    }

    return (
        <div className="admin-shell">
            <a className="skip-link" href="#main-content">
                Skip to main content
            </a>
            <aside className="sidebar">
                <div className="brand-lockup">
                    <img
                        className="company-logo"
                        src="https://www.siemens-energy.com/content/dam/siemensenergy-aem/images/logo/SE_Logo_White.png"
                        alt="Siemens Energy"
                    />
                    <div>
                        <strong>Oliver</strong>
                        <small>Initiative operations</small>
                    </div>
                </div>

                <nav className="primary-nav" aria-label="Primary navigation">
                    <p className="nav-label">Workspace</p>
                    <button
                        type="button"
                        className={workspace === "portfolio" ? "active" : ""}
                        aria-current={workspace === "portfolio" ? "page" : undefined}
                        title="Portfolio"
                        onClick={() => openWorkspace("portfolio")}>
                        <GridIcon />
                        <span>Portfolio</span>
                    </button>
                    <button
                        type="button"
                        className={workspace === "conversations" ? "active" : ""}
                        aria-current={workspace === "conversations" ? "page" : undefined}
                        title="Conversations"
                        onClick={() => openWorkspace("conversations")}>
                        <InboxIcon />
                        <span>Conversations</span>
                    </button>
                    {canTestAssessment ? (
                        <button
                            type="button"
                            className={workspace === "assessment" ? "active" : ""}
                            aria-current={workspace === "assessment" ? "page" : undefined}
                            title="Assessment lab"
                            onClick={() => openWorkspace("assessment")}>
                            <LabIcon />
                            <span>Assessment lab</span>
                        </button>
                    ) : null}
                </nav>

                <div className="sidebar-footer">
                    <span>Siemens Energy</span>
                    <small>Internal use only</small>
                </div>
            </aside>

            <div className="workspace">
                <header className="topbar">
                    <div className="topbar-heading">
                        <p className="eyebrow">
                            Oliver administration <span aria-hidden="true">/</span> {workspaceDetails[workspace].eyebrow}
                        </p>
                        <h1>{workspaceDetails[workspace].title}</h1>
                    </div>
                    <div className="admin-identity">
                        <span className="identity-avatar" aria-hidden="true">
                            {identityInitials(session.username)}
                        </span>
                        <span className="identity-copy">
                            <strong>{session.username}</strong>
                            <small>Authorized administrator</small>
                        </span>
                        <button type="button" onClick={() => void signOut()}>
                            Sign out
                        </button>
                        {signOutError ? <small role="alert">{signOutError}</small> : null}
                    </div>
                </header>
                <main id="main-content" tabIndex={-1}>
                    {workspace === "portfolio" ? (
                        initiativeId ? <InitiativeDetail key={initiativeId} initiativeId={initiativeId} onBack={() => openWorkspace("portfolio")} onOpenThread={openThread} /> : <Initiatives onOpenInitiative={openInitiative} />
                    ) : workspace === "conversations" ? (
                        <EmailThreads key={threadId || "conversation-inbox"} initialThreadId={threadId} onOpenInitiative={openInitiative} />
                    ) : (
                        <AssessmentLab />
                    )}
                </main>
            </div>
        </div>
    );
}

export default function App() {
    const [session, setSession] = useState<AdminSession | null | undefined>(undefined);

    useEffect(() => {
        void initializeAuthentication()
            .then(() => {
                configureAccessTokenProvider(getAccessToken);
                return api.getSession();
            })
            .then(setSession)
            .catch(() => setSession(null));
    }, []);

    if (session === undefined) {
        return <div className="app-loading">Loading Oliver admin…</div>;
    }
    if (session === null) {
        return <SignIn onAuthenticated={setSession} />;
    }
    return <Dashboard session={session} onSignedOut={() => setSession(null)} />;
}
