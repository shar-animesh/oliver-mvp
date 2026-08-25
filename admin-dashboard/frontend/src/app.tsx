// Path: src/app.tsx
// Description: Authenticated shell for the Oliver administration dashboard.

import { useEffect, useState, type FormEvent } from "react";

import { api, configureAccessTokenProvider, type AdminSession } from "./api";
import { authMode, getAccessToken, initializeAuthentication, signInWithEntra, signOutFromEntra } from "./auth";
import AssessmentLab from "./pages/assessment-lab";
import EmailThreads from "./pages/email-threads";
import Initiatives from "./pages/initiatives";

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
            <section className="signin-panel" aria-labelledby="signin-title">
                <img
                    className="signin-logo"
                    src="https://www.siemens-energy.com/content/dam/siemensenergy-aem/images/logo/SE_Logo_White.png"
                    alt="Siemens Energy"
                />
                <p className="eyebrow">Oliver administration</p>
                <h1 id="signin-title">Sign in to the lifecycle workspace</h1>
                <p className="signin-intro">Restricted access for authorized Oliver administrators.</p>
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
                <small>{authMode === "entra" ? "Access is governed by Microsoft Entra app roles." : "Local development authentication only."}</small>
            </section>
        </main>
    );
}

function Dashboard({ session, onSignedOut }: { session: AdminSession; onSignedOut: () => void }) {
    const [workspace, setWorkspace] = useState<"portfolio" | "conversations" | "assessment">("portfolio");
    const [signOutError, setSignOutError] = useState<string | null>(null);
    const canTestAssessment = session.roles.some((role) => role === "Oliver.Assessment.Test" || role === "Oliver.Platform.Admin");

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
            <aside className="sidebar">
                <div className="brand-lockup">
                    <img
                        className="company-logo"
                        src="https://www.siemens-energy.com/content/dam/siemensenergy-aem/images/logo/SE_Logo_White.png"
                        alt="Siemens Energy"
                    />
                    <div>
                        <strong>Oliver</strong>
                        <small>Assessment administration</small>
                    </div>
                </div>

                <nav className="primary-nav" aria-label="Primary navigation">
                    <p className="nav-label">Workspace</p>
                    <button type="button" className={workspace === "portfolio" ? "active" : ""} onClick={() => setWorkspace("portfolio")}>
                        <GridIcon />
                        Portfolio
                    </button>
                    <button type="button" className={workspace === "conversations" ? "active" : ""} onClick={() => setWorkspace("conversations")}>
                        <InboxIcon />
                        Conversations
                    </button>
                    {canTestAssessment ? (
                        <button type="button" className={workspace === "assessment" ? "active" : ""} onClick={() => setWorkspace("assessment")}>
                            <LabIcon />
                            Assessment lab
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
                    <div>
                        <p className="eyebrow">Oliver administration</p>
                        <h1>
                            {workspace === "portfolio"
                                ? "Initiative lifecycle"
                                : workspace === "conversations"
                                  ? "Conversations and assessments"
                                  : "Assessment laboratory"}
                        </h1>
                    </div>
                    <div className="admin-identity">
                        <span>{session.username}</span>
                        <button type="button" onClick={() => void signOut()}>
                            Sign out
                        </button>
                        {signOutError ? <small role="alert">{signOutError}</small> : null}
                    </div>
                </header>
                <main>{workspace === "portfolio" ? <Initiatives /> : workspace === "conversations" ? <EmailThreads /> : <AssessmentLab />}</main>
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
        return <div className="app-loading">Loading Oliver…</div>;
    }
    if (session === null) {
        return <SignIn onAuthenticated={setSession} />;
    }
    return <Dashboard session={session} onSignedOut={() => setSession(null)} />;
}
