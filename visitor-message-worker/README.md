# Visitor Message Worker

This Cloudflare Worker accepts website contact-form submissions and writes each one into a Notion database.

Flow:

`website form -> Cloudflare Worker -> Notion database`

## Why this setup

- The website stays static on GitHub Pages.
- The Notion token stays server-side inside Cloudflare secrets.
- Visitors can submit directly from the page without opening email.

## What the Worker expects

The website sends JSON like this:

```json
{
  "name": "Ada",
  "message": "Love the site.",
  "submitted_at": "2026-03-03T21:12:00.000Z",
  "site": "https://wenyuedai.github.io/protein_design_podcast/",
  "page_title": "Protein Design Podcast"
}
```

## Notion setup

1. Create a Notion integration.
2. Create a database to collect visitor messages.
3. Add one title property named `Name`.
4. Share that database with the integration.
5. Copy the integration token and the database ID.

The Worker writes:

- the title property as `Website message: <name>`
- the actual message as page content blocks
- submission timestamp and page URL as page content blocks

If your database uses a different title property name, set `NOTION_TITLE_PROPERTY`.

## Cloudflare setup

From this directory:

```bash
npm install
```

Set the secrets:

```bash
npx wrangler secret put NOTION_TOKEN
npx wrangler secret put NOTION_DATABASE_ID
```

Optional variables in `wrangler.toml`:

- `ALLOWED_ORIGIN`: the only browser origin allowed to submit
- `NOTION_TITLE_PROPERTY`: the title property name in your Notion database

Deploy:

```bash
npx wrangler deploy
```

After deploy, Cloudflare gives you a Worker URL such as:

`https://visitor-message-worker.<your-subdomain>.workers.dev`

## Connect the website

Rebuild the site with the Worker URL:

```bash
VISITOR_MESSAGE_ENDPOINT="https://visitor-message-worker.<your-subdomain>.workers.dev" \
python3 openclaw-knowledge-radio/tools/build_site.py
```

That bakes the Worker URL into the static site form.

## Security notes

- Do not put `NOTION_TOKEN` in the website code.
- Keep `ALLOWED_ORIGIN` limited to your real site origin.
- This Worker only accepts `POST` and `OPTIONS`.
