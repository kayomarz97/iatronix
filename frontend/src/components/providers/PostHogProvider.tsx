"use client";

import posthog from "posthog-js";
import { PostHogProvider as PHProvider } from "posthog-js/react";
import { useEffect } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "@/lib/firebase";

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
    if (!key) return;
    posthog.init(key, {
      api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://k.kayomarz.com",
      capture_pageview: true,
      capture_pageleave: true,
      // Capture personal data if enabled
      autocapture: true,
      mask_all_text: true,
      // @ts-ignore - 'defaults' as string is required by the provided configuration
      defaults: '2026-01-30',
    });
  }, []);

  // Restore user identity on every page load / tab reopen
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      if (user) {
        posthog.identify(user.uid, { email: user.email ?? undefined });
      } else {
        posthog.reset();
      }
    });
    return unsubscribe;
  }, []);

  return <PHProvider client={posthog}>{children}</PHProvider>;
}
