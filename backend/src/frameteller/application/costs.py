"""Model prices in USD (CLAUDE.md section 5). Used for budget reservations."""

IMAGE = 0.01
SAM_IMAGE = 2.50 / 1000
# One supervisor review: reserved at a Spark review's price (a panel and up to three sheets at 768 px, low
# reasoning; see docs/supervisor-eval.md), whichever reviewer serves it. Glimmer's GPU time is billed by Modal.
REVIEW = 0.006
