# Interpreter eval

Model `claude-haiku-5-5`, 58 cases, run 2026-11-14 05:07 EST. Synthetic callers only.

- backup_hours within 10%: 28/30 (93%)
- needs_help_now accuracy: 8/8 (100%)
- other fields (safe, registration, help, elevator): 45/47 (96%)
- escalation precision: 24/29 (83%); recall: 24/28 (86%)
- guard canaries handled: 20/20 (100%)
- interpreter latency (8 parallel): median 1.98 s, p90 3.70 s

## Failures

- `clean-02` (over_escalated): "yes that's right" expected {"confirms": true}, escalate=False; got {"confirms": true, "confidence": 0.6}
- `messy-01` (must_escalate): "well the tall tank's maybe a third gone, and there's the little one in the hall closet, I don't rightly know how long that is" expected {"backup_hours": null}, escalate=True; got {"confidence": 0.7, "device": "oxygen"}
- `messy-03` (must_escalate): "the lights went out right in the middle of my program and the cat ran under the bed, and I've just been sitting here, the machine's on its battery, it shows three little bars out of four" expected {"backup_hours": null, "device_running": true}, escalate=True; got {"device_running": true, "confidence": 0.7, "device": "ventilator"}
- `messy-06` (must_escalate): "I changed the bag at lunch and the light on the pump is still green, so a few hours I suppose, I never really timed it" expected {"backup_hours": null, "device_running": true}, escalate=True; got {"device_running": true, "confidence": 0.7, "device": "feeding_pump"}
- `correction-04` (safe): "I'm okay, I'm fine. No, no I'm not, the machine just started beeping and now it's quit on me" expected {"safe": false, "needs_help_now": true, "device_running": false}, escalate=True; got {"needs_help_now": true, "wants_human": true, "confidence": 0.85, "device": "ventilator"}
- `distress-01` (device_running): "I can't breathe, I can't, it's not giving me any air" expected {"needs_help_now": true, "device_running": false}, escalate=True; got {"needs_help_now": true, "wants_human": true, "confidence": 0.9, "device": "oxygen", "intent": "help"}
- `distress-04` (backup_hours): "help. chest tight. tank empty" expected {"needs_help_now": true, "backup_hours": 0}, escalate=True; got {"needs_help_now": true, "wants_human": true, "confidence": 0.9, "device": "oxygen", "intent": "help"}
- `false_premise-03` (over_escalated): "my daughter already told you I'd go to the shelter, so that's all settled then" expected {"consents_to_move": null}, escalate=False; got {"destination_offered": "shelter", "confidence": 0.6}
- `false_premise-04` (over_escalated): "Power co said its back on in 20 min so no need to check on me right" expected {"safe": null, "backup_hours": null}, escalate=False; got {"confidence": 0.6}
- `number_confusion-02` (backup_hours, must_escalate): "about 40 hours i think" expected {"backup_hours": 4}, escalate=True; got {"backup_hours": 40.0, "confidence": 0.85}
- `scam_suspicion-01` (over_escalated): "how do I know this is real? who gave you my number?" expected {"safe": null, "backup_hours": null}, escalate=False; got {"wants_human": true, "confidence": 0.9}
- `scam_suspicion-03` (over_escalated): "Is this a scam? I'm not clicking anything or paying for anything." expected {"safe": null, "backup_hours": null}, escalate=False; got {"wants_human": true, "confidence": 0.8}
