# Stage 3A — SMS Provider Comparison (Research Only)

**Date:** 2026-09-29
**Scope:** This is a read-only research deliverable. No files in the project were modified, no packages were installed, no accounts were created, no credentials were generated, and no provider API was called. This report does not choose or rank a provider — that decision is left to you.

**Method:** Information below comes from each provider's own official documentation/website where available (linked inline as sources), supplemented by web search results from third-party pricing-comparison sites where official numbers were not publicly published. Every claim below is tagged with its source type. Where public documentation did not clearly state something, this report says so explicitly rather than guessing or estimating.

---

## Providers compared

1. **MSG91** — India-headquartered CPaaS, one of the most widely used OTP/transactional SMS providers for Indian developers and startups.
2. **Twilio** — US-headquartered global CPaaS, the most widely known general-purpose SMS/voice API platform, with documented India-specific routing rules.
3. **Exotel** — India-headquartered CPaaS, chosen as the third option because it publishes unusually detailed, developer-facing documentation specifically covering DLT, Unicode/Kannada/Hindi SMS, and delivery-status codes — which made it possible to verify claims against primary sources rather than third-party blog summaries.

---

## 1. MSG91

| Dimension | Findings |
|---|---|
| **India SMS availability** | Yes — MSG91 is an India-domiciled provider; India-to-India transactional and OTP SMS is its core product. |
| **OTP/transactional SMS support** | Confirmed. MSG91 has a dedicated OTP product (historically "SendOTP") with `send`, `verify`, and `retry` operations, plus general transactional SMS via DLT template IDs. |
| **DLT requirements** | Confirmed mandatory for India, consistent with TRAI regulation generally. MSG91's own docs describe checking "SMS API and DLT Parameters" and matching template variables exactly (case-sensitive) to the DLT-approved template. Full entity/sender-ID/template registration steps were not laid out in one place in the pages fetched — **not fully confirmed from a single public documentation page**, though the requirement itself is confirmed. |
| **Sender ID support** | Confirmed — customizable sender IDs are supported; numeric sender IDs for promotional routes require `route=1` in the request payload. Availability of specific sender ID formats depends on destination and DLT approval. |
| **Kannada/Hindi Unicode SMS support** | MSG91 publishes a help article on "How to send Unicode custom SMS by CSV," confirming Unicode SMS sending is supported. However, the specific pages fetched did not explicitly enumerate Kannada or Hindi by name, character-limit behavior, or an `EncodingType`-style parameter — **exact parameter name and per-language confirmation not found in the pages reviewed; marked not confirmed from public documentation**. |
| **API simplicity** | Documented as a REST API with an `authkey` header and template-variable substitution; described in MSG91's own integration guide as straightforward, with multi-language code samples in their API docs (docs.msg91.com). |
| **Python integration difficulty** | An official MSG91-org GitHub repository (`MSG91/sendotp-python`, `pip install sendotp`) exists for the older OTP-specific product, providing `send()`, `verify()`, `retry()` methods. For **general transactional SMS** (not OTP-only), no MSG91-maintained Python package was found; several third-party PyPI packages exist (`msg91-py`, `msg91-client`, `msg91-sms`) but none confirmed as officially maintained by MSG91 — **official general-SMS Python SDK status not confirmed**. In practice, MSG91's plain REST API can be called from Python with the standard `requests` library regardless. |
| **Authentication method** | Static `authkey` (API key) passed in the request header/payload. |
| **Delivery status/webhook support** | Confirmed and well-documented: MSG91 supports webhooks for OTP delivery reports and SMS delivery reports, configured from the dashboard ("On Report Received" event), delivering a JSON payload with request ID, delivery status/failure reason, recipient circle, timestamps, credits used, and DLT template ID. |
| **Retry/error handling capabilities** | The `sendotp-python` library exposes an explicit `retry()` method for OTP resend. The delivery-report webhook includes a "retry counts" field, implying retry tracking exists. Provider-side automatic retry policy (e.g., on operator timeout) was **not confirmed from public documentation reviewed**. |
| **Test credits/sandbox/development availability** | MSG91 offers a "Startup Offer" (Startup Balance): 25,000 transactional SMS/month and 25,000 OTP SMS/month free for 6 months. Eligibility requires a **private/corporate domain email** (Gmail/Yahoo/Outlook explicitly rejected) **and** formal association with an approved startup accelerator/incubator/VC partner, plus displaying an MSG91 badge on the applicant's website. **This makes the startup offer very unlikely to be usable by an individual college student without an eligible organizational affiliation.** A separate, lower-tier free-trial credit for ordinary new sign-ups may exist but could not be confirmed from the pages reached (the direct "credits" help page returned a 404 during this research). |
| **Whether external account required** | Yes — MSG91 dashboard sign-up required. |
| **Realistic for a college project?** | Plausible for demonstrating real OTP/SMS delivery at low volume using pay-as-you-go credit, but the free Startup Offer is realistically **not** available to an individual student project without an accelerator/incubator affiliation. DLT registration is still required for India domestic routing, which is the same regulatory burden every India-routing provider carries. |
| **Important limitations/uncertainties** | Exact Unicode/Kannada parameter behavior not confirmed from the pages reviewed. No confirmed officially-maintained general-purpose Python SDK. Ordinary (non-startup) trial credit amount not confirmed. DLT template/entity registration workflow only partially detailed in the pages fetched. |

**Sources (MSG91):**
- [OTP Pricing in India | MSG91-India](https://msg91.com/in/pricing/otp)
- [How can I integrate API provided in MSG91 panel? | MSG91](https://knowledgebase.msg91.com/how-can-i-integrate-api-provided-in-msg91-panel-)
- [Check your SMS API and DLT Parameters](https://msg91.com/help/dlt-registration-in-india/check-your-sms-api-and-dlt-parameters)
- [How to send Unicode custom SMS by CSV?](https://msg91.com/help/how-to-send-unicode-custom-sms-by-csv)
- [How to Receive SendOTP API Delivery Reports via Webhook](https://msg91.com/help/webhook-new/how-to-receive-otp-delivery-reports-via-webhook)
- [How to Receive SMS Delivery Reports via Webhook (New)](https://msg91.com/help/webhook-new/how-to-receive-sms-delivery-reports-via-webhook-new)
- [GitHub – MSG91/sendotp-python](https://github.com/MSG91/sendotp-python)
- [MSG91 for Startups](https://msg91.com/startups)
- [msg91-py · PyPI](https://pypi.org/project/msg91-py/) (third-party, unconfirmed official status)

---

## 2. Twilio

| Dimension | Findings |
|---|---|
| **India SMS availability** | Confirmed, via two distinct routes: **international route** (no DLT needed, sender ID replaced by a random 5–9 digit number, outbound-only, bypasses India DND) and **domestic route** (requires DLT registration, alphanumeric sender ID preserved with a 2-letter operator prefix, ~10 business days to provision). |
| **OTP/transactional SMS support** | Confirmed — transactional messaging supported through DLT-registered alphanumeric sender IDs on the domestic route; Twilio also has a separate Verify API product for OTP specifically (not audited in depth here, but referenced in Twilio's own trial docs as "40 verifications" included in trial). |
| **DLT requirements** | Confirmed mandatory **only for the domestic route**; the international route explicitly bypasses DLT and India's DND registry, at the cost of one-way-only messaging and a masked, unpredictable sender number. This is a meaningful architectural trade-off not present in India-native providers. |
| **Sender ID support** | Domestic: alphanumeric sender ID, pre-registration required, operator-prefixed (e.g., "VM-TWILIO"). International: long codes only, sender ID is **not preserved** — replaced by a random number, and recipients cannot reply. Short codes supported on both routes with 4–6 week provisioning. |
| **Kannada/Hindi Unicode SMS support** | Confirmed — both international and domestic routes support UCS-2 (Unicode) encoding, enabling Indian-language messaging. Twilio's guidelines page states this explicitly, without listing a script-by-script limitation. |
| **API simplicity** | Twilio's REST API and official `twilio-python` SDK are widely documented as simple: a `client.messages.create(to=, from_=, body=)`-style call. Confirmed via Twilio's own developer blog/tutorials and general public documentation. |
| **Python integration difficulty** | Low. Official, actively maintained SDK: `pip install twilio` (`github.com/twilio/twilio-python`). This is the most clearly "official and confirmed" Python integration path of the three providers compared. |
| **Authentication method** | Account SID + Auth Token (or API Key/Secret pair), passed via the SDK or HTTP Basic Auth on the REST API. |
| **Delivery status/webhook support** | Confirmed and extensively documented — `StatusCallback` parameter on the Messages API, dedicated messaging-webhooks guide, and a support article specifically on "Tracking the Delivery Status of an Outbound Twilio SMS or MMS Message." This is the most thoroughly documented delivery-status system of the three. |
| **Retry/error handling capabilities** | Not independently verified in depth in this pass beyond the existence of documented delivery/error statuses in the Messages resource and webhook guides; Twilio is widely known for a mature error-code catalog, but specific automatic-retry policy details were **not fetched/confirmed in this research session**. |
| **Test credits/sandbox/development availability** | Confirmed and clearly documented: trial account includes **100 free SMS**, 100 WhatsApp messages, 75 voice minutes, 40 Verify checks, no credit card required. Trial restricts sending to a maximum of **5 verified recipient numbers**, restricts to pre-defined message templates (no custom text), and restricts SMS/calls to the sign-up country. Trial expires after 30 days. |
| **Whether external account required** | Yes — Twilio Console sign-up. |
| **Realistic for a college project?** | Yes, with an important caveat: the trial's "5 verified numbers only" and "no custom message text" restrictions mean a demo can only realistically be shown to a handful of pre-verified phone numbers (e.g., the student's own number and a few teammates'/testers'), not an open citizen base, unless the account is upgraded to paid. The international route (no DLT) is the only way to send freely without DLT registration, but it is one-way-only and the sender number is not stable/brandable. |
| **Important limitations/uncertainties** | Exact current per-SMS price to India was only found as a general international rate (see pricing note below) — the page fetched did not clearly separate a standalone "India-specific" published per-message rate from the general international rate table, and pricing pages themselves state prices "may change... without notice." Retry/error-handling policy details not independently confirmed in this pass. |

**Pricing note (Twilio):** The pricing page fetched (`twilio.com/en-us/sms/pricing/in`) returned a general **$0.0832 per outbound message** figure tied to "international numbers and alphanumeric sender IDs," plus phone number rental from $1.15/month. It explicitly states prices may change without notice and recommends contacting sales for exact current/volume rates — **treat this as indicative, not a firm quote**.

**Sources (Twilio):**
- [India: SMS Guidelines | Twilio](https://www.twilio.com/en-us/guidelines/in/sms)
- [Limitations sending SMS messages to Indian mobile devices – Twilio Support](https://support.twilio.com/hc/en-us/articles/223134167-Limitations-sending-SMS-messages-to-Indian-mobile-devices)
- [SMS Pricing in India for Text Messaging | Twilio](https://www.twilio.com/en-us/sms/pricing/in)
- [Twilio trial account | Twilio](https://www.twilio.com/docs/usage/trials)
- [Messaging Webhooks | Twilio](https://www.twilio.com/docs/usage/webhooks/messaging-webhooks)
- [Tracking the Delivery Status of an Outbound Twilio SMS or MMS Message](https://support.twilio.com/hc/en-us/articles/360008989454-Tracking-the-Delivery-Status-of-an-Outbound-Twilio-SMS-or-MMS-Message)
- [GitHub – twilio/twilio-python](https://github.com/twilio/twilio-python)

---

## 3. Exotel

| Dimension | Findings |
|---|---|
| **India SMS availability** | Confirmed — Exotel is an India-headquartered CPaaS; India domestic SMS is a core product. |
| **OTP/transactional SMS support** | Confirmed — dedicated SMS API with transactional, promotional, and OTP message types documented separately, OTP described as receiving "priority delivery." |
| **DLT requirements** | Confirmed mandatory and unusually well-documented: Exotel's own docs state plainly that without DLT registration, "your SMS will be blocked by telecom operators," covering transactional, promotional, **and** OTP SMS alike. Exotel documents a clear 3-step process — Entity Registration (3–7 days), Sender ID Registration (1–3 days), Template Registration (1–3 days) — with named accepted DLT portals (Jio TrueConnect, Vodafone-Idea ViLPower, Airtel, BSNL, MTNL, Smartping). This is the most detailed and explicit DLT documentation of the three providers reviewed. |
| **Sender ID support** | Confirmed — sender ID/header registration is part of the documented DLT flow; specific sender ID format constraints beyond DLT approval were not examined in further depth in this pass. |
| **Kannada/Hindi Unicode SMS support** | Confirmed and unusually explicit: Exotel's docs list supported Indian-language scripts by name, **including Hindi and Kannada** (plus Tamil, Telugu, Malayalam, Bengali, Gujarati, Marathi, Odia, Punjabi/Gurmukhi), state the exact API parameter (`EncodingType=unicode`), and warn that sending Unicode content with the default `EncodingType=plain` will garble non-Latin characters. This is the most specific, directly relevant confirmation of Kannada/Hindi support found for any of the three providers. |
| **API simplicity** | REST API with Basic Auth embedded in the endpoint URL (`https://<api_key>:<api_token>@api.exotel.com/v1/Accounts/<account_sid>/Sms/send`), documented with a "Quickstart: Send Your First SMS" guide. |
| **Python integration difficulty** | No officially Exotel-maintained Python SDK was found. Several **unofficial/community** Python wrappers exist (`pyexotel`, `ExotelPy`, `exotel-python` by NooraHealth, `sarathsp06/exotel-py`) — none confirmed as officially maintained by Exotel. The REST API itself is simple enough to call directly via `requests` in Python without an SDK. |
| **Authentication method** | HTTP Basic Auth using API Key + API Token, embedded in the request URL alongside the Account SID. |
| **Delivery status/webhook support** | Confirmed and well-documented — dedicated "SMS Delivery Reports," "SMS Webhooks," and "SMS Status Codes" documentation pages. Supports both a per-message `StatusCallback` parameter and an account-level default callback URL, plus on-demand polling via an SMS Details API. Documents granular `DetailedStatus` codes (e.g., `DELIVERED_TO_HANDSET`=20000, `FAILED_DLT_TEMPLATE`=30001, `FAILED_DND`=30004, `FAILED_INVALID_NUMBER`=30005, `FAILED_OPERATOR`=30010). This is the most granular status-code documentation found among the three. |
| **Retry/error handling capabilities** | Exotel's own best-practices documentation explicitly recommends "handling retries with idempotent endpoints" and monitoring elevated failure rates using the detailed status codes — meaning Exotel documents this as the **integrator's** responsibility (client-side retry logic), rather than describing an automatic provider-side retry guarantee. This differs from an assumption of automatic retries and should be treated as a design responsibility on the student's side. |
| **Test credits/sandbox/development availability** | Confirmed — free 7-day trial with complimentary call/SMS credits and one trial virtual number (ExoPhone). Trial restricts outbound calls/SMS to a **maximum of 10 whitelisted numbers**, and explicitly excludes bulk SMS, campaigns, WhatsApp API, and custom caller ID. Credits are non-transferable and expire at trial end. After the 7-day period, sending stops immediately (configuration persists 30 days before deletion). |
| **Whether external account required** | Yes — Exotel dashboard sign-up (`my.exotel.com/auth/register`). |
| **Realistic for a college project?** | Yes for a short, scoped demo (10 whitelisted numbers is enough for a classroom/panel demonstration), but the 7-day trial window is short relative to a multi-week project timeline — the student would likely need to either request a trial extension via support or upgrade before final demonstration/evaluation. |
| **Important limitations/uncertainties** | No officially confirmed Python SDK (community wrappers only). Specific numeric SMS/OTP pricing was **not found on the public pricing documentation page** — Exotel's own docs defer to "contact Exotel Sales or check your account dashboard" for exact rates, so **pricing is not confirmed from public documentation** for this provider, unlike MSG91 (which publishes tiered OTP pricing) and Twilio (which publishes an indicative per-message rate). |

**Sources (Exotel):**
- [Unicode SMS | Exotel Developer Docs](https://developer.exotel.com/docs/sms-support/unicode-sms)
- [DLT Registration | Exotel Developer Docs](https://developer.exotel.com/docs/sms-support/dlt-registration)
- [SMS Pricing | Exotel Developer Docs](https://developer.exotel.com/docs/sms-support/sms-pricing)
- [SMS Delivery Reports | Exotel Developer Docs](https://developer.exotel.com/docs/sms-support/sms-delivery-reports)
- [SMS Webhooks | Exotel Developer Docs](https://developer.exotel.com/docs/sms-support/sms-webhooks)
- [SMS Status Codes | Exotel Developer Docs](https://developer.exotel.com/docs/sms-support/sms-status-codes)
- [Trial Account Features and Limitations | Exotel Developer Docs](https://developer.exotel.com/docs/getting-started/trial-account)
- [Sender ID (Header) | Exotel Developer Docs](https://developer.exotel.com/docs/sms-support/sender-id)
- [pyexotel · PyPI](https://pypi.org/project/pyexotel/1.0.2) (unofficial, community-maintained)

---

## Neutral comparison table

| Dimension | MSG91 | Twilio | Exotel |
|---|---|---|---|
| India SMS availability | Yes (India-native) | Yes (int'l + domestic routes) | Yes (India-native) |
| OTP/transactional support | Yes, dedicated OTP product | Yes (SMS + separate Verify API) | Yes, dedicated OTP type |
| DLT mandatory | Yes (confirmed, process only partly detailed in pages reviewed) | Yes for domestic route only; international route bypasses DLT | Yes (confirmed, most detailed 3-step process found) |
| Sender ID support | Yes, incl. numeric via `route=1` | Domestic: alphanumeric (registered). International: not preserved (random number) | Yes, tied to DLT registration flow |
| Kannada/Hindi Unicode support | Unicode confirmed generally; Kannada/Hindi not individually confirmed in pages reviewed | Unicode (UCS-2) confirmed for both routes, not broken down by script | Kannada **and** Hindi explicitly named, with exact `EncodingType=unicode` parameter documented |
| API simplicity | REST + authkey header, documented as simple | REST + mature SDK, widely documented as simple | REST + Basic Auth in URL, quickstart guide available |
| Python integration | Official SDK exists only for OTP product (`sendotp-python`); no confirmed official general-SMS SDK | Official, actively maintained `twilio-python` SDK | No official SDK; community wrappers only |
| Authentication method | Static `authkey` | Account SID + Auth Token / API Key-Secret | API Key + API Token via HTTP Basic Auth in URL |
| Delivery status/webhooks | Yes, dashboard-configured webhook with detailed JSON payload | Yes, `StatusCallback` param + dedicated webhook guides (most extensively documented) | Yes, per-message or account-level callback + granular numeric status codes |
| Retry/error handling | OTP `retry()` method exists; provider-side auto-retry policy not confirmed | Documented status/error codes; specific retry policy not confirmed in this pass | Explicitly documented as the **integrator's** responsibility (idempotent client-side retries) |
| Free test path | "Startup Offer" (25k SMS/mo, 6 mo) gated behind accelerator/incubator affiliation — not confirmed accessible to an individual student; ordinary trial credit amount not confirmed | 100 free SMS, 5 verified numbers max, 30-day trial, no card required | 7-day trial, 10 whitelisted numbers, free credits, no bulk/WhatsApp |
| Published pricing | Yes — tiered OTP pricing published (₹0.25 down to ₹0.18 per OTP by volume) | Indicative rate published (~$0.0832/msg, "subject to change") | Not confirmed from public documentation — provider defers to sales/dashboard |
| External account required | Yes | Yes | Yes |
| Realistic for an individual student project | Plausible on pay-as-you-go; free-tier startup offer likely inaccessible without an accelerator affiliation | Plausible; trial's 5-number cap limits an open demo but is fine for a supervised classroom demo | Plausible for a short scoped demo; 7-day trial window is tight against a multi-week project unless extended |

---

## What this report deliberately does not do

- It does not recommend or rank a provider.
- It does not call any provider's API, create any account, or generate any credential.
- It does not assume pricing, retry behavior, or language support beyond what the fetched pages stated; every gap is marked "not confirmed from public documentation" rather than estimated.
- It does not modify any file in the project.

The choice among MSG91, Twilio, and Exotel — and whether to route through Twilio's international vs. domestic path, if Twilio is chosen — is yours to make. Each has a genuinely different trade-off shape: MSG91 is India-native with published OTP pricing but weaker confirmed Python/Unicode documentation; Twilio has the most mature Python SDK and delivery-status tooling but the most India-specific routing complexity (and its DLT-free international route is one-way-only); Exotel has the most explicit Kannada/Hindi and DLT documentation of the three but no confirmed official Python SDK and unpublished pricing.
