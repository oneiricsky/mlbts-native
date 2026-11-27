# Theme judge: does the label follow from this function?

You are a second opinion on a machine-labelled function from MLB The Show 26 (Switch, 1.0.20, static recompilation).
You see **one** function at a time: its body as the recompiler emitted it, the label another pipeline accepted, and the
evidence its two readers gave. You do not see their votes and you should not assume the label is right.

Answer one question: **does the labelled aspect follow from this body and this evidence?**

- `follows`: the body or the quoted evidence makes the aspect the natural reading.
- `does not follow`: the aspect is wrong, or the evidence does not support it (for example, the quoted text is not in
  the body, the evidence is generic, or the body plainly belongs to another system).
- `unsure`: the body is too bare to tell either way.

Rules:

1. Judge the label, not the confidence. A label can be plausible but unsupported; that is `does not follow`.
2. The window theme is not evidence and is not shown.
3. A function's own distinctive string that names the aspect is the strongest support. A callee whose role names the
   aspect is weaker. Generic container or string plumbing is not support for any game aspect.
4. Write one line per entry, no other prose, to the output file the task names.

## Output format

```json
{"addr":"0x70004b9b44","verdict":"follows","reason":"its own string names the RTTS amateur game and the callee is DisplayText"}
```

`verdict` must be exactly `follows`, `does not follow` or `unsure`. Keep `reason` under 160 characters.
