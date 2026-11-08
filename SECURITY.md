# Security

Thank you for looking. We take every report seriously.

## Report a vulnerability

Please tell us privately. Don't open a public issue, discussion or pull request.

- **On GitHub:** open the **Security** tab of this repository and choose **Report a vulnerability**.
- **By email:** [security@0x1audio.com](mailto:security@0x1audio.com).

Tell us what you found, the steps to reproduce it, what an attacker could do with it, and the version or commit you tested. If you'd like credit, tell us the name to use.

## What's in scope

- **The `mixel` command:** `new`, `check`, `test` and `dev`, for example a way to make `mixel check` pass an app that breaks the rules review relies on.
- **The MCP server** and the docs it serves, including anything that would tell someone to install a package we didn't name.
- **The cloud client:** how it sends and keeps tokens.

The desktop sandbox, file access, registry review, and the API and auth live in the Mixel cloud, and its [SECURITY.md](https://github.com/0x1audio/cloud/blob/main/SECURITY.md) covers them. If you're not sure where something belongs, report it here and we'll pass it on.

Not in scope: denial of service by volume, spam, social engineering, scanner output without a way to cause harm, and bugs in dependencies (report those upstream, and tell us if we're affected).

## What happens next

| Step | Our target |
| --- | --- |
| We confirm we got your report | within 3 working days |
| We tell you whether we can reproduce it and how severe we think it is | within 10 working days |
| We fix a critical issue | within 14 days |
| We fix a high-severity issue | within 30 days |
| We fix everything else | within 90 days |

We'll update you at least every two weeks. When the fix ships, we publish a GitHub security advisory and credit you, unless you'd rather stay anonymous. Please keep the details private until then, or for 90 days, whichever comes first. We're a small team and don't run a paid bug bounty yet.

## Safe harbour

If you research in good faith and follow this page, we consider your research authorised. We won't take legal action against you or report you to the police, and if someone else does, we'll say you acted with our permission. Good faith means testing on your own accounts, data and computer, stopping and telling us if you reach anyone else's data, not degrading any service for others, and giving us the time above before you talk about it publicly.

## Supported versions

We fix security problems on `main` and in the latest release only.
