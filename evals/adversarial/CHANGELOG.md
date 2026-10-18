# Classifier fix log (rules pass of `classify_reason`)

Measured by running the real `core/reasons.py` + `reasons.yaml` old vs new on the UNCHANGED 84 reason cases
(`cases.jsonl`, sha256 pinned in `baseline.json`). Rules only; the LLM fallback was not exercised.

## What changed
1. Whole-word matching (with simple inflections s/es/ed/d/ing): "other" no longer matches "another/mother/bother", "broken" no longer matches "unbroken".
2. Negation: a keyword negated by a nearby word in the same clause ("not damaged", "nothing faulty", "no longer defective") does not count. "not only X" is not negation. Keywords that already start with a negator ("not received", "no refund") are exempt.
3. Longest phrase wins: "not received" inside "refund not received" is dropped in favour of the longer phrase.
4. Conflict: two or more different specific classes matched -> abstain for human review (`conflict:a|b`) instead of first-keyword-wins. A specific class beats the generic `other` class.
5. Multi-issue marker ("also", "as well as", "in addition"...) alongside a keyword -> human review.
6. Code-mixed (Hinglish) text: English keyword rules are not trusted; rules are skipped (LLM still runs if configured).
7. Data: removed the bare keyword "other" from the `other` class (exact CODE "other" is unchanged); added British spellings of existing keywords ("did not authorise", "unrecognised transaction").

## Outcome on the 13 keyword-trap cases (previously 12 confident wrong answers)
| Outcome | Count | Cases |
| :-- | --: | :-- |
| Now correct | 4 | r039 (longest match), r040 (negation), r042 (whole word), r044 (negation + spelling variant) |
| Now abstain: rules cannot read it | 6 | r041, r043, r045, r046, r047, r050 (the false keyword is gone; no true keyword remains) |
| Now abstain: code-mixed guard | 2 | r048, r049 |
| Confident wrong | 0 | |

So "12 -> 0 wrong" is 4 genuine fixes and 8 abstentions. Rules-only coverage on this category fell 100% -> 38%.
r044 is also helped by the spelling-variant keyword, which is a general fix but did flip a case from this set.

## Trade-offs and regressions (all measured)
- r080 (instruction injected into the reason text) went correct -> abstain: the injected class name now conflicts with the real "not received" keyword. Arguably desirable, but it is a coverage loss.
- Ambiguous cases answered instead of routed to a human: 3/8 -> 1/8. One genuinely ambiguous case is still answered ("not as described and the refund has not come": the refund half has no keyword).
- Project synthetic sets: clean 150/150 correct (unchanged); messy 6 correct / 4 wrong / 90 abstain -> 6 / 0 / 94.
- Plain-English paraphrases, Hinglish, typos and non-Latin text: still 100% abstain on rules alone. They depend on the LLM fallback, which is unmeasured here (`--llm`).

## Not claimed
Zero wrong answers on 13 hand-written traps is not a real-world error rate. These cases were written by the same author as the fixes, and the
regression cases were written knowing the mechanisms. A truly held-out set (ideally real disputes) is still needed.
