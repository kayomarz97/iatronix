# Security Policy

Iatronix is a medical information tool. We take security seriously and appreciate
responsible disclosure.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security problems.**

Report suspected vulnerabilities privately to: **kayomarz97@gmail.com**
(You may prefix the subject with `SECURITY:`.)

Please include:
- A description of the issue and its potential impact
- Steps to reproduce (proof-of-concept if possible)
- Any relevant logs, requests, or screenshots

We aim to acknowledge reports within a few business days and will keep you updated
on remediation progress. Please give us a reasonable window to fix the issue before
any public disclosure.

## Scope

In scope: the Iatronix web application (med.kayomarz.com), its API, and this source
repository.

Out of scope: denial-of-service / volumetric testing, social engineering, and
automated scanning that generates significant load. Please do not run load tests or
fuzzers against the live service — reach out first if you need to test something that
could affect availability or cost.

## Data & medical disclaimer

Iatronix does not provide medical advice and is not a substitute for professional
clinical judgment. Do not submit real patient-identifying information.
