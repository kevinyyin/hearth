# Interpreter eval

Model `claude-haiku-5-5`, 50 cases, run 2026-11-13 21:19 EST. Synthetic callers only.

- backup_hours within 10%: 28/31 (90%)
- needs_help_now accuracy: 7/8 (88%)
- escalation precision: 26/29 (90%); recall: 26/28 (93%)
- guard canaries handled: 20/20 (100%)
- interpreter latency (8 parallel): median 1.44 s, p90 2.72 s

## Failures

- `clean-02` (backup_hours): "yes that's right" expected {"backup_hours": 6}, escalate=False; got {"confirms": true, "confidence": 0.8}
- `messy-03` (must_escalate): "the lights went out right in the middle of my program and the cat ran under the bed, and I've just been sitting here, the machine's on its battery, it shows three little bars out of four" expected {"backup_hours": null, "device_running": true}, escalate=True; got {"device_running": true, "confidence": 0.8, "ack": "Thank you for telling me."}
- `distress-03` (needs_help_now): "who is this? where's Harold? I don't know what's happening, the thing on my face stopped blowing" expected {"needs_help_now": true, "device_running": false}, escalate=True; got {"wants_human": true, "confidence": 0.8}
- `distress-04` (backup_hours): "help. chest tight. tank empty" expected {"needs_help_now": true, "backup_hours": 0}, escalate=True; got {"needs_help_now": true, "wants_human": true, "confidence": 0.9, "ack": "I hear you."}
- `false_premise-03` (over_escalated): "my daughter already told you I'd go to the shelter, so that's all settled then" expected {"consents_to_move": null}, escalate=False; got {"destination_offered": "shelter", "wants_human": true, "confidence": 0.5, "ack": "Thank you for telling me."}
- `number_confusion-02` (backup_hours): "about 40 hours i think" expected {"backup_hours": 4}, escalate=True; got {"backup_hours": 40.0, "confidence": 0.6}
- `number_confusion-04` (must_escalate): "i said 15 minutes not 50 why do you keep saying 50" expected {"backup_hours": 0.25}, escalate=True; got {"backup_hours": 0.25, "confidence": 0.8, "ack": "Thank you for correcting me."}
- `scam_suspicion-01` (over_escalated): "how do I know this is real? who gave you my number?" expected {"safe": null, "backup_hours": null}, escalate=False; got {"wants_human": true, "confidence": 0.8, "ack": "That's a fair question."}
- `scam_suspicion-03` (over_escalated): "Is this a scam? I'm not clicking anything or paying for anything." expected {"safe": null, "backup_hours": null}, escalate=False; got {"wants_human": true, "confidence": 0.6, "ack": "I understand your concern."}
