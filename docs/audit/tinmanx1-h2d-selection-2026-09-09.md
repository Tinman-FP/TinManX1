# H2D Selection Handoff

Revision: `v2026.09.09-printer-handoff.1`.

## Evidence

A September 9 macOS crash occurred on a background thread inside the user's
locally installed Bambu networking plug-in, version `02.07.01.63`. The main
thread was idle in the application event loop. The plug-in stack is stripped;
the report does not establish the precise internal vendor defect.

Application logs show a deterministic problem in TinManX1 before that crash:

1. The Prepare preset changes from Creality K2 Plus to Bambu H2D.
2. DeviceManager starts selecting H2D, but notifies sidebar observers before
   updating its `selected_machine` member.
3. The observer reads the old K2 selection. Building its displayed filament
   list changes the global printer agent back to Creality and connects it.
4. H2D selection repeats, producing the same reversal. The Bambu agent is
   disconnected/reselected repeatedly during its connection startup.
5. H2D status arrives, followed by the native plug-in crash.

This also matches the wrong-device filament matching visible in the log:
K2 spool inventory was matched against the newly selected H2D preset family.
Private logs, printer addresses, serials and credentials are not included here.

## Correction

- Commit the selected device before notifying observers.
- Make filament-list construction and display read only. They consume the
  supplied MachineObject's cached data and cannot select or connect an agent.
- Keep HTTP/pull inventory refresh in the explicit Sync command. This retains
  Qidi, Snapmaker and Creality synchronization, uses the machine's TLS choice,
  and reports a failed refresh instead of reusing stale inventory as success.
- Display the new device's cached inventory on selection for either sync mode,
  so the previous device's slots are not left visible.
- Treat assignment of the same cached printer agent as a no-op, avoiding
  unnecessary callback replacement while the plug-in is running.

No plug-in replacement, profile retuning, credential reset, or printer firmware
change is part of this correction. Native plug-in faults cannot be recovered
with a C++ exception handler. This change removes the observed application-side
connection churn; it does not claim to repair all possible vendor-library bugs.

## Verification

The new GUI source-contract checks failed in all three cases before the fix:
selection notification ordering, passive inventory display, and explicit pull
refresh ownership. These complement live GUI acceptance; they do not substitute
for executing wxWidgets or the proprietary plug-in.

The native injected-agent test also failed before the fix: 20 repeat selections
rewrote the live queue callback 20 additional times. The test additionally covers
switching away and back, old callback clearing, new callback dispatch, and null
assignment preserving the current agent.

The Release build passes. All three GUI source contracts pass after the fix.
The standard native, FFF and offline utility suites pass 360 cases / 263,402
assertions, including the new 15-assertion injected-agent test. Release and
FibreSeek checks pass. The existing manifest verifies all 936 curated repository
and installed profile resources; none are rewritten.

Installation and live acceptance results are recorded in the associated pull
request after verification. No result here certifies an unattended print or all
possible proprietary plug-in behavior.
