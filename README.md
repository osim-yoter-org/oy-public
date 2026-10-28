# oy-public

Public runtime data for https://osimyoter.co.il. Edit a file here and the site picks it up within about 5 minutes. No site deploy is needed.

## links.json: short links
`https://osimyoter.co.il/?<slug>` and `https://osimyoter.co.il/<slug>` forward to `url`.

```json
{
  "<slug>": {
    "url": "https://destination.example/path",
    "label": "Text shown while forwarding (optional)",
    "delayMs": 0
  }
}
```

Rules:
- A slug uses lowercase a-z, 0-9 and `-` only.
- A slug must not be the name of a real site page (for example `u`, `wa`, `ads`, `search`, `pp`). If it is, the site page wins and the link is ignored.
- `url` must start with `https://`.
- `delayMs` is optional. 0 forwards at once; 3000 shows the label for 3 seconds first.
- Remove a line to retire a link. After that, the slug shows the site's 404 page.

## whatsapp-groups-json.json
The WhatsApp group list that `/wa` picks from.

## latest_ad.json
The ad card shown on the `/wa` forwarding screen.

Every file must be valid JSON. Check yours with a JSON validator before you commit.
