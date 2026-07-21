"use client";

// Google sign-in with SAFE merge into an existing email/password account.
//
// Firebase deliberately does NOT auto-link a password account to Google. When a
// user signs in with Google for an email that already has a password account, it
// throws `auth/account-exists-with-different-credential` and hands us the email +
// the pending Google credential. We only merge AFTER the user proves ownership by
// entering their existing password — result: ONE account (one uid), both methods.
//
// NB: we intentionally do NOT use `fetchSignInMethodsForEmail` — it is deprecated
// and returns empty once email-enumeration-protection is on (default for projects
// created after 2023-09-15). The error already carries everything we need.

import {
  GoogleAuthProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  linkWithCredential,
  setPersistence,
  browserLocalPersistence,
  browserSessionPersistence,
  type AuthCredential,
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
