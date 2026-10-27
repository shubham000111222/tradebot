# Emergency runbook

Keep a copy of this page on your phone. Paper mode is the safe place to rehearse it.

## If something looks wrong

1. Stop adding risk. Do not open trades manually.
2. Check the exchange status, dashboard Risk page, and the last 50 log lines.
3. If the bot responds, use the configured flatten command.
4. If it does not respond, create `KILL` in the project folder. The watchdog converts it to a persistent L2 flatten state.
5. Check the exchange directly: cancel open orders, inspect balances and positions, and close anything unprotected.
6. If credentials may be compromised, revoke the API key, change the exchange password, and rotate 2FA.
7. Record the incident using the template below.
8. Do not restart until the cause is understood and reconciliation is clean.

Stopping a container does not cancel exchange orders or close positions.

## Diagnosis checklist

- Exchange status page and maintenance notices
- Internet connectivity
- UTC clock/NTP synchronization
- Disk space, CPU and memory
- Last deployment and config change
- Kill-switch level and reason
- Local/exchange balance and open-order reconciliation

## Incident template

```text
Time: UTC / IST
Mode:
What was observed:
Trigger:
Bot actions:
Operator actions:
PnL impact:
Root cause:
Fix:
Regression test added:
```

Rehearse the runbook monthly in paper mode and before any live go/no-go review.
