// Path: src/auth.ts
// Description: Local/Entra authentication bootstrap and access-token acquisition.

import { InteractionRequiredAuthError, PublicClientApplication, type AccountInfo } from "@azure/msal-browser";

export const authMode = import.meta.env.VITE_ADMIN_AUTH_MODE === "entra" ? "entra" : "local";

const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID as string | undefined;
const clientId = import.meta.env.VITE_ENTRA_SPA_CLIENT_ID as string | undefined;
const apiScope = import.meta.env.VITE_ENTRA_API_SCOPE as string | undefined;

const msal =
    authMode === "entra" && tenantId && clientId
        ? new PublicClientApplication({
              auth: {
                  clientId,
                  authority: `https://login.microsoftonline.com/${tenantId}`,
                  redirectUri: window.location.origin,
              },
              cache: { cacheLocation: "sessionStorage" },
          })
        : null;

function requireEntraConfiguration(): PublicClientApplication {
    if (!msal || !apiScope) {
        throw new Error("The Entra SPA client and API scope are not configured.");
    }
    return msal;
}

function activeAccount(application: PublicClientApplication): AccountInfo | null {
    return application.getActiveAccount() || application.getAllAccounts()[0] || null;
}

export async function initializeAuthentication(): Promise<void> {
    if (authMode !== "entra") return;
    const application = requireEntraConfiguration();
    await application.initialize();
    const redirect = await application.handleRedirectPromise();
    const account = redirect?.account || activeAccount(application);
    if (account) application.setActiveAccount(account);
}

export async function signInWithEntra(): Promise<void> {
    const application = requireEntraConfiguration();
    const result = await application.loginPopup({ scopes: [apiScope!] });
    application.setActiveAccount(result.account);
}

export async function signOutFromEntra(): Promise<void> {
    if (!msal) return;
    await msal.logoutPopup({ account: activeAccount(msal) || undefined });
}

export async function getAccessToken(): Promise<string | null> {
    if (authMode !== "entra") return null;
    const application = requireEntraConfiguration();
    const account = activeAccount(application);
    if (!account) return null;
    try {
        const result = await application.acquireTokenSilent({ account, scopes: [apiScope!] });
        return result.accessToken;
    } catch (reason) {
        if (!(reason instanceof InteractionRequiredAuthError)) throw reason;
        const result = await application.acquireTokenPopup({ account, scopes: [apiScope!], claims: reason.claims });
        application.setActiveAccount(result.account);
        return result.accessToken;
    }
}
