# Credits

`/watch` was created by **[Bradley Bonanno](https://github.com/bradautomates)** at
[bradautomates/claude-video](https://github.com/bradautomates/claude-video), MIT licensed.
This fork exists only because upstream has been inactive since 2026-06-30; all of the
original design and implementation is his.

## Ported contributions

Fixes written by other contributors, submitted upstream and still unmerged there. Each is
cherry-picked with its original git authorship intact, so `git log` and the GitHub commit
page credit the author, not this fork. Please thank them on their upstream PR.

> Note: @OpenClawLinda's commit email is not registered to their GitHub account, so
> GitHub renders the author name without a profile link. The credit is theirs; the
> link is here and in the commit message.

| Upstream PR | Author | What it fixes |
|---|---|---|
| [#214](https://github.com/bradautomates/claude-video/pull/214) | [@nbkwabi](https://github.com/nbkwabi) | Stops one provider's API key being sent to the other provider's endpoint |
| [#225](https://github.com/bradautomates/claude-video/pull/225) | [@OpenClawLinda](https://github.com/OpenClawLinda) | Collapses YouTube rolling auto-captions that shipped every line twice |
| [#226](https://github.com/bradautomates/claude-video/pull/226) | [@OpenClawLinda](https://github.com/OpenClawLinda) | Uniform sampling spreads across the range instead of only the head |
| [#236](https://github.com/bradautomates/claude-video/pull/236) | [@gth-spec](https://github.com/gth-spec) | Flags transcript proper nouns as unverified, so names get checked against frames |
| [#221](https://github.com/bradautomates/claude-video/pull/221) | [@oheewono](https://github.com/oheewono) | Prefers human-authored caption tracks over auto-generated ones |
| [#235](https://github.com/bradautomates/claude-video/pull/235) | [@charles98601-sg](https://github.com/charles98601-sg) | Caches downloads by URL so a repeat run skips the fetch |

If you are one of these authors and would prefer your work not be carried here, open an
issue and it will be removed.
