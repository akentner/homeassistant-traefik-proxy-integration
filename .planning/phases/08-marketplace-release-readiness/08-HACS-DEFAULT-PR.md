# Draft: catalog submission to `hacs/default`

For the user (M8). Nothing here has been done by an agent: no fork, no branch,
no PR. Submit only after the v1.0.0 release exists and both validators passed
on GitHub.

Source of the list and the template: read anonymously on 2026-11-15 from
`hacs/default` branch `master` at commit
`d1bec9610a340580ccacf958b0790ba20f7629b3` (2026-11-10):
`integration` (5165 entries, a JSON array) and `.github/PULL_REQUEST_TEMPLATE.md`.
Re-read both right before you submit; the list grows daily.

## Preconditions (all must be true before opening the PR)

- [ ] `feat/marketplace-polish` is merged to `main`.
- [ ] The `Validate` workflow passed on `main` after the merge, with all five
      jobs green, in particular **HACS validation** (`hacs/action`, category
      `integration`, no `ignore`) and **hassfest**. The HACS job is the first
      complete run of all 10 hacs/action checks on this tree (REL-07 was
      deferred to CI; it is not proven locally).
- [ ] Tag `v1.0.0` exists and the GitHub release "Traefik Proxy 1.0.0" is
      published with the body from `08-RELEASE-NOTES-v1.0.0.md`, as a full
      release marked as the latest release (not a pre-release). The
      pre-release `v1.0.0-rc1` does not count: its manifest version is
      1.0.0-rc1. The `Release check` workflow (tag equals manifest version)
      passed.
- [ ] The repository is public, not archived, has a description, topics,
      issues enabled and the MIT licence (all green on 2026-11-15).

## Steps

1. Fork `hacs/default` **from your personal account** (not from an
   organisation): <https://github.com/hacs/default/fork>.
2. In the fork, create a branch from `master`, for example
   `add-traefik-proxy-integration`.
3. Open the file `integration` and add exactly this line:

   ```json
     "akentner/homeassistant-traefik-proxy-integration",
   ```

   Insertion point (the list is sorted case-insensitively; verified with
   `sorted(list, key=str.casefold) == list`):

   ```json
     "akasma74/Hass-Custom-Alarm",
     "akentner/homeassistant-kroki-integration",
     "akentner/homeassistant-traefik-proxy-integration",
     "akinin/ha_keenetic",
   ```

   i.e. directly **after** `"akentner/homeassistant-kroki-integration"` and
   directly **before** `"akinin/ha_keenetic"`. Keep the two-space indentation
   and the trailing comma. The repository is not in the list yet (checked
   case-insensitively).
4. Commit with a short message, for example
   `Add akentner/homeassistant-traefik-proxy-integration`.
5. Open the pull request against `hacs/default:master` with the title and body
   below.
6. **Request no reviews** from anyone. The template states that a review request
   closes the PR.
7. Wait for the bot checks on the PR (they run the HACS validation against the
   repository). Fix any finding in this repository, publish a new release if
   needed and update the links. Review by the HACS maintainers can take months;
   do not ping.

## PR title

```
Add akentner/homeassistant-traefik-proxy-integration
```

## PR body (template of `hacs/default`, filled in)

Replace the three markers before submitting:

- `<RELEASE_URL>`: URL of the published v1.0.0 release, e.g.
  `https://github.com/akentner/homeassistant-traefik-proxy-integration/releases/tag/v1.0.0`
- `<HACS_ACTION_RUN_URL>`: URL of a passing `Validate` run on `main` whose
  "HACS validation" job is green (Actions tab -> run -> job link)
- `<HASSFEST_RUN_URL>`: URL of the same run's green "hassfest" job

```markdown
<!--
DO NOT REQUEST REVIEWS, THAT IS JUST RUDE, IF YOU DO THE PULL REQUEST WILL BE CLOSED!
Make sure to check out the guide here: https://hacs.xyz/docs/publish/start
-->
## Checklist

<!-- Do not open a pull request before you have completed all these, it will be closed. -->

- [x] I've read the [publishing documentation](https://hacs.xyz/docs/publish/start).
- [x] I've added the [HACS action](https://hacs.xyz/docs/publish/action) to my repository.
- [x] (For integrations only) I've added the [hassfest action](https://developers.home-assistant.io/blog/2020/04/16/hassfest/) to my repository.
- [x] The actions are passing without any disabled checks in my repository.
- [x] I've added a link to the action run on my repository below in the links section.
- [x] I've created a new release of the repository after the validation actions were run successfully.

## Links

<!-- Do not open a pull request before you have provided all these, it will be closed. -->

Link to current release: <RELEASE_URL>
Link to successful HACS action (without the `ignore` key): <HACS_ACTION_RUN_URL>
Link to successful hassfest action (if integration): <HASSFEST_RUN_URL>

<!-- tid:73253df5-5376-4e68-8c16-b234da6a2de3 -->
```

Notes on the filled fields:

- Tick a box only when it is true at submission time. "The actions are passing"
  and "new release after the validation actions" depend on the preconditions
  above; if the HACS job has not passed yet, do not submit.
- Keep the template's `tid` comment unchanged; the bot uses it.
- `hacs/action` runs in `validate.yml` without an `ignore` key (category
  `integration`); hassfest runs as `home-assistant/actions/hassfest`.

## Open item before submission

- **Logo trademark (assumption A3/A8, open):** the logo is the Traefik Proxy
  dashboard lockup (MIT-licensed artwork from `traefik/traefik`); Traefik Labs'
  trademark guidelines have not been reviewed. Decide before submitting whether
  to keep the logo or ship only the icon (see `08-DRAFT-PR.md`, "Decision for
  the user").
