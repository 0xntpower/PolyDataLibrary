"""Production-grade skip-decision tuner.

Collects SkipRecord entries from bot.log files across sessions and searches
for tuning changes that would have produced a statistically credible
positive-PnL strategy over the historical skip population.
"""
