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

## איך מוסיפים קישור קצר
1. לפתוח את הטופס [בקשה לקישור קצר חדש](https://github.com/osim-yoter-org/oy-public/issues/new?template=new-short-link.yml) ולמלא שם קישור, כתובת יעד וטקסט.
2. לחכות דקה: בדיקה אוטומטית פותחת Pull Request ומוסיפה קישור אליו בתגובה. אם יש בעיה, היא מופיעה בתגובה; לתיקון לערוך את הבקשה.
3. אני מאשר את ה-Pull Request (merge).
4. הקישור עולה לאוויר כ-5 דקות אחרי האישור.

Operator: the form needs the `short-link` label (`gh label create short-link -R osim-yoter-org/oy-public`) and Settings > Actions > General > "Allow GitHub Actions to create and approve pull requests" turned on. Request PRs are opened with the workflow token, so GitHub does not run the Validate check on them; the request workflow runs the same validator before it opens the PR and puts the result in the PR body. Validate still runs on PRs opened by people and on every push to main.

## whatsapp-groups-json.json
The WhatsApp group list that `/wa` picks from.

## latest_ad.json
The ad card shown on the `/wa` forwarding screen.

Every file must be valid JSON. Check yours with a JSON validator before you commit.
