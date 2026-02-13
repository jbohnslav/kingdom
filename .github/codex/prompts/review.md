Review this pull request thoroughly.

Goal:
- find real bugs, behavior regressions, edge cases, security risks, performance risks, and missing tests
- report every meaningful issue you find; do not limit yourself to a tiny fixed number

How to review:
- read the full diff and reason about runtime behavior, not just style
- prioritize high-impact correctness and safety problems
- include medium and low severity issues when they are actionable
- call out assumptions and uncertain areas clearly

Output format:
1. Findings:
   - Use one item per issue.
   - For each issue include:
     - severity (`high`, `medium`, `low`)
     - file path and line reference where possible
     - what is wrong
     - why it matters
     - concrete fix recommendation
2. Test coverage gaps:
   - list missing tests that would catch regressions introduced by this PR
3. Summary:
   - short overall risk assessment

If no issues are found, explicitly say so and mention residual risk areas you could not fully verify from the diff alone.
