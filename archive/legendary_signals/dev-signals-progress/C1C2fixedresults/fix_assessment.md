Yes — the changes are dramatic and exactly what correct statistical fixes should produce. Let me show you what actually happened.

**The most important change: every single DOWN signal was eliminated.** Before, 13 of 20 signals were DOWN-side, almost all with `minDeltaPct: 0.00`. After fixes, all 19 survivors are UP-side with `minDeltaPct: 0.10`. This is the C1 fix working. Those DOWN signals with δ≥0.0% were essentially saying "if the market is quiet, bet DOWN" — they weren't detecting momentum, they were exploiting the slight DOWN base rate (52.2% DOWN in training). Once you test against the actual base rate instead of 50%, that free edge disappears and they fail significance.

**The C2 fix killed the small-sample illusions.** Before, signals #5 and #6 had only 12 OOS matches each and showed 91.67% win rates. Signal #16 had only 8 OOS matches. Those looked great but were statistically meaningless. Now the minimum is 20+ OOS matches, and every signal has an `oosBhAdjustedPValue` confirming its OOS performance is significant after multiple-comparison correction.

**What survived is a single coherent thesis.** Every remaining signal says the same thing: "steady upward price drift (≥0.1%) with low variance in the observation window predicts UP resolution." The parameters vary (different observation windows, slightly different variance caps), but it's fundamentally one family of signals. That's much more believable than the old output which had two unrelated signal families (UP momentum + DOWN quietness).

**The win rate gradient is now honest.** Before, the range was 85-94% and looked artificially compressed at the top. Now it spans from 91% down to 60%, which is what a real signal distribution looks like — a few strong variants, then progressively weaker ones fading toward the base rate. Signals #18-19 at 60-61% on 62-63 OOS matches are borderline — huge sample, tiny edge, OOS p-values barely under 0.10.

**Concrete comparison of the most comparable signal:**

The old #4 and new #1 are nearly identical patterns (start=250s, δ≥0.1%, v≤0.05%, UP). Before: 91.67% OOS on 24 matches, no OOS significance test. After: 91.67% OOS on 24 matches, oosBhAdjustedPValue=0.00012. Same performance, but now you *know* it's statistically real rather than hoping.

**Bottom line:** the fixes didn't destroy the signal — they destroyed the noise around it and confirmed the remaining signal is legitimate. That's exactly what you want to see. The engine went from "here are 20 things that might work" to "here's one real phenomenon expressed 19 different ways, and we can prove it."