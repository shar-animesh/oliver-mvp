// Path: src/app.tsx
// Description: Authenticated shell for the Oliver administration dashboard.

import { useEffect, useState, type FormEvent } from "react";

import { api, configureAccessTokenProvider, type AdminSession } from "./api";
import { authMode, getAccessToken, initializeAuthentication, signInWithEntra, signOutFromEntra } from "./auth";
import { SIEMENS_ENERGY_LOGO } from "./assets/siemens-energy-logo";
import AssessmentLab from "./pages/assessment-lab";
import EmailThreads from "./pages/email-threads";
import InitiativeDetail from "./pages/initiative-detail";
import Initiatives from "./pages/initiatives";
import Intelligence from "./pages/intelligence";

type Workspace = "portfolio" | "conversations" | "assessment" | "patterns" | "scout";

type LocationState = { workspace: Workspace; initiativeId: string | null; threadId: string | null };

function locationState(): LocationState {
    const segments = window.location.pathname.split("/").filter(Boolean);
    const candidate = segments[0] as Workspace | undefined;
    const workspace: Workspace = candidate === "conversations" || candidate === "assessment" || candidate === "patterns" || candidate === "scout" || candidate === "portfolio" ? candidate : "portfolio";
    const id = segments[1] || null;
    return { workspace, initiativeId: workspace === "portfolio" ? id : null, threadId: workspace === "conversations" ? id : null };
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

function PatternIcon() {
    return (
        <svg aria-hidden="true" viewBox="0 0 20 20">
            <path d="M3 4.5h14v2H3v-2Zm0 4.5h9v2H3V9Zm0 4.5h14v2H3v-2Z" />
        </svg>
    );
}

function ScoutIcon() {
    return (
        <svg aria-hidden="true" viewBox="0 0 20 20">
            <path d="m10 2.2 6.7 7.8-6.7 7.8L3.3 10 10 2.2Zm0 2.3L5.6 10l4.4 5.5 4.4-5.5L10 4.5Z" />
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
                        <img className="siemens-energy-logo" src={SIEMENS_ENERGY_LOGO} alt="Siemens Energy" />
                        <span className="brand-divider" aria-hidden="true" />
                        <span className="oliver-wordmark">Oliver<small>Initiative operations</small></span>
                    </div>
                    <div className="signin-story-copy">
                        <p className="eyebrow">Siemens Energy / internal workspace</p>
                        <h1>Review pilot decisions with clarity.</h1>
                        <p>One place for pilot progress, evidence, assessments and governed actions.</p>
                    </div>
                    <div className="signin-story-footer">
                        <span className="secure-indicator"><i /> Secure administrator access</span>
                        <span>Oliver v1.0</span>
                    </div>
                </section>
                <section className="signin-panel" aria-labelledby="signin-title">
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
    const initialLocation = locationState();
    const [workspace, setWorkspace] = useState<Workspace>(initialLocation.workspace);
    const [initiativeId, setInitiativeId] = useState<string | null>(initialLocation.initiativeId);
    const [threadId, setThreadId] = useState<string | null>(initialLocation.threadId);
    const [signOutError, setSignOutError] = useState<string | null>(null);
    const canTestAssessment = session.roles.some((role) => role === "Oliver.Assessment.Test" || role === "Oliver.Platform.Admin");

    useEffect(() => {
        const syncWorkspace = () => {
            const next = locationState();
            setWorkspace(next.workspace);
            setInitiativeId(next.initiativeId);
            setThreadId(next.threadId);
        };
        window.addEventListener("popstate", syncWorkspace);
        return () => window.removeEventListener("popstate", syncWorkspace);
    }, []);

    function openWorkspace(nextWorkspace: Workspace, options: { initiativeId?: string; threadId?: string } = {}): void {
        const id = nextWorkspace === "portfolio" ? options.initiativeId : nextWorkspace === "conversations" ? options.threadId : undefined;
        const pathname = `/${nextWorkspace}${id ? `/${encodeURIComponent(id)}` : ""}`;
        window.history.pushState(null, "", pathname);
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
                    <img className="siemens-energy-logo" src={SIEMENS_ENERGY_LOGO} alt="Siemens Energy" />
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

                <nav className="primary-nav secondary-nav" aria-label="Intelligence navigation">
                    <p className="nav-label">Intelligence</p>
                    <button
                        type="button"
                        className={workspace === "patterns" ? "active" : ""}
                        aria-current={workspace === "patterns" ? "page" : undefined}
                        title="Patterns across initiatives"
                        onClick={() => openWorkspace("patterns")}>
                        <PatternIcon />
                        <span>Patterns</span>
                    </button>
                    <button
                        type="button"
                        className={workspace === "scout" ? "active" : ""}
                        aria-current={workspace === "scout" ? "page" : undefined}
                        title="Scout candidate queue"
                        onClick={() => openWorkspace("scout")}>
                        <ScoutIcon />
                        <span>Scout</span>
                    </button>
                </nav>

                <div className="sidebar-footer">
                    <div className="sidebar-account">
                        <span className="identity-avatar" aria-hidden="true">{identityInitials(session.username)}</span>
                        <div className="sidebar-account-copy">
                            <strong>{session.username}</strong>
                            <small>Authorized administrator</small>
                        </div>
                        <button className="sidebar-signout" type="button" onClick={() => void signOut()} aria-label="Sign out">
                            <svg aria-hidden="true" viewBox="0 0 20 20"><path d="M8 3.5h7.5v13H8V15h6V5H8V3.5ZM3 9.25h7v1.5H3v-1.5Zm2.75-3 1.06 1.06L4.87 9.25h5.13v1.5H4.87l1.94 1.94-1.06 1.06L2 10l2.75-2.75Z" /></svg>
                            <span>Sign out</span>
                        </button>
                    </div>
                    {signOutError ? <small className="sidebar-signout-error" role="alert">{signOutError}</small> : null}
                    <div className="sidebar-legal">
                        <span>Siemens Energy</span>
                        <small>Internal use only</small>
                    </div>
                </div>
            </aside>

            <div className="workspace">
                <main id="main-content" tabIndex={-1}>
                    {workspace === "portfolio" ? (
                        initiativeId ? <InitiativeDetail key={initiativeId} initiativeId={initiativeId} onBack={() => openWorkspace("portfolio")} onOpenThread={openThread} /> : <Initiatives onOpenInitiative={openInitiative} onOpenThread={openThread} />
                    ) : workspace === "conversations" ? (
                        <EmailThreads key={threadId || "conversation-inbox"} initialThreadId={threadId} onOpenInitiative={openInitiative} onOpenThread={openThread} />
                    ) : workspace === "assessment" ? (
                        <AssessmentLab />
                    ) : (
                        <Intelligence mode={workspace} onOpenInitiative={openInitiative} adminName={session.username} />
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
