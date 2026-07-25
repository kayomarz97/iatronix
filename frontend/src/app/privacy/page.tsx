import type { Metadata } from "next";
import { LegalPage, Section, Callout, Bullets } from "@/components/legal/LegalPage";

export const metadata: Metadata = {
  title: "Privacy Policy — Iatronix",
  description: "What Iatronix collects, why, where it is stored, and how to delete it.",
};

// NOTE FOR MAINTAINERS: every factual claim below is drawn from the codebase
// (models/user.py, services/keystore, PostHogProvider.tsx, services/retention.py,
// data_fetcher.py). If you change what is stored or who it is sent to, update this page in
// the same commit — a privacy policy that lies is worse than none.
// Items marked [REVIEW] need the owner's legal/jurisdictional input before launch.

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy" updated="25 July 2026">
      <Callout>
        <strong style={{ color: "var(--text-primary)" }}>Draft pending legal review.</strong> This
        page accurately describes how Iatronix handles data today, but it has not been reviewed by
        a lawyer. Items marked [REVIEW] are still to be confirmed.
      </Callout>

      <Section heading="Who we are">
        <p>
          Iatronix is an evidence-based clinical reference tool operated by [REVIEW: legal entity
          name and registered address]. For any privacy question or request, contact [REVIEW:
          contact email].
        </p>
      </Section>

      <Section heading="What we collect">
        <p>Only what you give us, plus basic usage analytics:</p>
        <Bullets
          items={[
            <>
              <strong>Account</strong> — your email address. Your password is handled entirely by
              Google Firebase Authentication; Iatronix never receives or stores it. If you sign in
              with Google, we receive your email address and Google account identifier.
            </>,
            <>
              <strong>Profile you enter</strong> — username, full name, country, professional
              position, institution, institution type, specialty, age and gender. All of these are
              optional and can be changed or cleared at any time in Settings.
            </>,
            <>
              <strong>Newsletter consent</strong> — recorded only if you tick the box, and only
              used to decide whether to email you.
            </>,
            <>
              <strong>Your searches</strong> — clinical queries you run and the answers returned,
              stored so you can see your own search history.
            </>,
            <>
              <strong>API keys you supply</strong> — see &quot;Your API keys&quot; below.
            </>,
            <>
              <strong>Usage analytics</strong> — page views and interaction events via PostHog, to
              understand which features are used. Analytics are linked to your account identifier
              and email. Text content on pages is masked before capture.
            </>,
          ]}
        />
        <p>
          We do <strong>not</strong> ask for, and you should not enter, any patient-identifiable
          information. Iatronix is a reference tool for clinicians, not a place to record patient
          data.
        </p>
      </Section>

      <Section heading="Your API keys">
        <p>
          Iatronix is bring-your-own-key. When you supply an API key for an AI provider, it is
          encrypted before being written to our database (Fernet symmetric encryption) and is
          decrypted only in memory, at the moment a request is made on your behalf. Keys are never
          logged and are never returned to the browser — the interface only ever shows whether a
          key is set. You can delete a stored key at any time from Settings.
        </p>
        <p>
          Your queries are sent to whichever AI provider your key belongs to (for example Cerebras,
          Anthropic, OpenAI or OpenRouter). Their handling of that data is governed by their own
          privacy policies, not this one.
        </p>
      </Section>

      <Section heading="Who we share it with">
        <p>We do not sell your data. We share it only with the services required to run Iatronix:</p>
        <Bullets
          items={[
            <>
              <strong>Google Firebase</strong> — authentication (email/password and Google sign-in).
            </>,
            <>
              <strong>Google Cloud Platform</strong> — hosting, database and backups, in the{" "}
              <code>us-central1</code> region.
            </>,
            <>
              <strong>PostHog</strong> — product analytics.
            </>,
            <>
              <strong>Your chosen AI provider</strong> — receives the text of your clinical query,
              authenticated with your own API key.
            </>,
          ]}
        />
        <p>
          Iatronix also queries public medical databases — including PubMed/NCBI, openFDA, RxNorm,
          DailyMed, MedlinePlus, NICE, ClinicalTrials.gov, Semantic Scholar and ChEMBL — to retrieve
          evidence. These requests carry your search terms but no account information.
        </p>
      </Section>

      <Section heading="How long we keep it">
        <p>
          Account and profile data are kept while your account exists. Older query and search-history
          records are periodically archived to encrypted cloud storage and then deleted from the
          live database. [REVIEW: state the exact retention period you want to commit to.]
        </p>
      </Section>

      <Section heading="Your rights">
        <p>
          You can view and edit your profile, and add or delete stored API keys, at any time from
          Settings. To request a copy of your data, correction, or full deletion of your account,
          contact [REVIEW: contact email]. Depending on where you live, you may also have the right
          to object to processing, restrict it, or complain to a data-protection authority.
        </p>
      </Section>

      <Section heading="Cookies and local storage">
        <p>
          Iatronix uses browser storage to keep you signed in and to remember interface preferences
          such as your theme. PostHog sets cookies to distinguish repeat visits. We do not use
          advertising cookies.
        </p>
      </Section>

      <Section heading="Changes">
        <p>
          If we change what we collect or who we share it with, we will update this page and its
          &quot;last updated&quot; date.
        </p>
      </Section>
    </LegalPage>
  );
}
