"use client";

// Google sign-in, account linking, and password recovery.
//
// Firebase ranks providers as "trusted" or "untrusted" and the ranking decides what
// happens when the same email arrives via a second provider
// (https://firebase.google.com/docs/auth/users):
//
//   trusted   = Google for @gmail.com, Yahoo for @yahoo.com, Microsoft for
//               @outlook.com/@hotmail.com, Apple
//   untrusted = every other OAuth domain, AND "Email / Password without email
//               verification"
//
//   untrusted -> untrusted : throws auth/account-exists-with-different-credential
//   trusted   -> untrusted : throws auth/account-exists-with-different-credential
//   untrusted -> TRUSTED   : "The trusted provider OVERWRITES the untrusted provider"
//                            — silently, with NO error to catch
//   trusted   -> trusted   : both link, no error
//
// That third row is the one that bites: an UNVERIFIED password account whose owner
// then signs in with Google on a @gmail.com address loses its password credential
// outright. The uid and all app data survive; only the password door is removed.
// startGoogleSignIn() below can only handle the rows that actually throw — the
// silent-overwrite row is prevented at registration (we now send a verification
// email, which promotes password to "trusted") and repaired by
// linkPasswordToCurrentUser() from Settings.
//
// NB: we intentionally do NOT use `fetchSignInMethodsForEmail` — it is deprecated
// and returns empty once email-enumeration-protection is on (default for projects
// created after 2023-09-15). The error already carries everything we need.

import {
  GoogleAuthProvider,
  EmailAuthProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  reauthenticateWithPopup,
  sendPasswordResetEmail,
  linkWithCredential,
  setPersistence,
  browserLocalPersistence,
  browserSessionPersistence,
  type AuthCredential,
  type User,
  type UserCredential,
} from "firebase/auth";
import { auth } from "@/lib/firebase";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";
import posthog from "posthog-js";

async function completeSignIn(cred: UserCredential, method: string) {
  const user = cred.user;
  const token = await user.getIdToken();
  localStorage.setItem(API_KEY_STORAGE_KEY, token);
  localStorage.setItem("iatronix_email", user.email || "");
  try {
    posthog.identify(user.uid, { email: user.email ?? undefined });
    posthog.capture("user_logged_in", { method });
  } catch {
    /* analytics is best-effort */
  }
  window.location.href = "/";
}

export type MergePrompt = { email: string; pendingCred: AuthCredential };

/**
 * Start Google sign-in.
 *   returns null       -> signed in, redirecting.
 *   returns MergePrompt -> a password account already exists for this email; the
 *                          caller must collect the password and call linkGoogleToPassword().
 * throws on genuine errors (popup closed, network, etc.).
 */
export async function startGoogleSignIn(rememberMe: boolean): Promise<MergePrompt | null> {
  await setPersistence(auth, rememberMe ? browserLocalPersistence : browserSessionPersistence);
  try {
    const cred = await signInWithPopup(auth, new GoogleAuthProvider());
    await completeSignIn(cred, "google");
    return null;
  } catch (err: any) {
    if (err?.code === "auth/account-exists-with-different-credential") {
      const pendingCred = GoogleAuthProvider.credentialFromError(err);
      const email = err?.customData?.email;
      if (pendingCred && email) return { email, pendingCred };
    }
    throw err;
  }
}

/** Verify the existing password, then link Google into the SAME account. */
export async function linkGoogleToPassword(
  email: string,
  password: string,
  pendingCred: AuthCredential,
) {
  const result = await signInWithEmailAndPassword(auth, email, password);
  await linkWithCredential(result.user, pendingCred);
  await completeSignIn(result, "google_linked");
}

/** Which sign-in methods are currently attached to this account. */
export function providerIds(user: User | null): string[] {
  return user?.providerData.map((p) => p.providerId) ?? [];
}

export function hasPasswordProvider(user: User | null): boolean {
  return providerIds(user).includes("password");
}

/**
 * Attach an email/password credential to the CURRENTLY SIGNED-IN account, so a
 * Google-only user can also sign in with email + password. One account, two doors.
 *
 * This is the repair path for accounts whose password was overwritten by the
 * untrusted -> trusted rule documented at the top of this file.
 *
 * Firebase requires a recent login before changing credentials; on
 * `auth/requires-recent-login` we re-prove identity via the Google popup and retry
 * once, so the user never sees a dead end.
 */
export async function linkPasswordToCurrentUser(password: string): Promise<void> {
  const user = auth.currentUser;
  if (!user) throw new Error("You are signed out. Sign in again and retry.");
  if (!user.email) throw new Error("This account has no email address on file.");

  const credential = EmailAuthProvider.credential(user.email, password);
  try {
    await linkWithCredential(user, credential);
  } catch (err: any) {
    if (err?.code !== "auth/requires-recent-login") throw err;
    await reauthenticateWithPopup(user, new GoogleAuthProvider());
    await linkWithCredential(user, credential);
  }
  // Providers changed — refresh the cached ID token so the backend sees current claims.
  localStorage.setItem(API_KEY_STORAGE_KEY, await user.getIdToken(true));
}

/**
 * "I forgot my password" reset.
 *
 * Verified 2026-07-25 against this project's own Firebase: the reset is accepted for a
 * GOOGLE-ONLY account too (accounts:sendOobCode returns 200 and the mail is delivered),
 * so completing it sets a password on an account that had none. That makes this a second
 * recovery route alongside linkPasswordToCurrentUser() — useful when the user cannot get
 * in at all and so cannot reach Settings.
 *
 * Callers must NOT branch on the outcome: with email-enumeration protection on, this
 * resolves successfully whether or not the address exists. Reporting the difference would
 * turn the login form into an enumeration oracle.
 */
export async function requestPasswordReset(email: string): Promise<void> {
  await sendPasswordResetEmail(auth, email);
}
