# Draft: logo-use request to Traefik Labs

Status: draft, **not sent**. Created 2026-11-20 after the logo licence review
(see `docs/BRAND.md`, "Trademark", and release 1.0.1).

## Background

- Copyright: the brand images are exported from `traefik/traefik`
  (`webui/src/components/icons/Logo.tsx`, tag v3.7.19), MIT licence. The MIT
  notice ships in `custom_components/traefik_proxy/brand/LICENSE.md`.
- Trademark: no public Traefik Labs trademark policy was found on 2026-11-20.
  The press kit (<https://traefik.io/press>) contains the same Traefik Proxy
  lockups, including the white-wordmark variant on dark backgrounds.
- The request is optional. Nothing blocks on it.

## Channel

No dedicated trademark contact was found. Options:

- the contact on <https://traefik.io/press> (private), or
- a GitHub Discussion in `traefik/traefik` (public).

## Text

```text
Subject: Using the Traefik Proxy logo in a community Home Assistant integration

Hello Traefik Labs team,

I maintain an open-source (MIT) Home Assistant custom integration that shows
the state of a Traefik Proxy instance (routers, services, certificate expiry)
inside Home Assistant:
https://github.com/akentner/homeassistant-traefik-proxy-integration
It is an independent community project and is not affiliated with or endorsed
by Traefik Labs.

To identify the software it connects to, the integration ships the Traefik
Proxy icon and the horizontal "traefik proxy" logo as brand images. They are
exported from the logo components of the Traefik Proxy dashboard
(traefik/traefik, webui/src/components/icons/Logo.tsx, MIT licence) without
changes to the artwork. For dark themes there is one variant with a white
wordmark, as the dashboard and your brand guide show. The MIT notice ships
with the integration, and the README states that Traefik is a trademark of
Traefik Labs.

Is this use acceptable to you, or would you prefer different assets or
attribution wording? I will adjust or remove the images on request.

Best regards,
Alexander Kentner
```

## After an answer

- Approval: record it in `docs/BRAND.md` ("Trademark") with date and channel.
- Different assets or wording requested: change `brand/` and the README
  accordingly and ship a patch release.
- Objection: replace the images with neutral artwork and ship a patch release.
