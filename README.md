# ✍️ GrammarHelp

A free, open-source alternative to Grammarly that runs entirely in your browser.
No account, no subscription, no server, no tracking.

## Features

- **Real-time checking** as you type, with color-coded underlines in the editor
- **One-click fixes** for each suggestion, or **Accept all**
- **Five categories:** spelling, grammar, punctuation, style and clarity
- **Writing score, readability (Flesch), word count and reading time**
- **Private by default:** the built-in checker never sends your text anywhere
- **Optional deep check** using [LanguageTool](https://languagetool.org)'s free API
  for thousands of extra grammar rules, a full spell-checker and 10+ languages
- Works offline, supports dark mode and phone-sized screens, and saves your draft locally

### What the built-in checker catches

| Category    | Examples |
|-------------|----------|
| Spelling    | ~100 common misspellings (`recieve`, `definately`, `teh`, `alot`) |
| Grammar     | `a`/`an` (with exceptions like *an hour* and *a university*), repeated words, lowercase `i`, sentence capitalization, `could of`, `then`/`than`, `your`/`you're`, `its`/`it's`, `their`/`there`, `to`/`too`, `loose`/`lose` |
| Punctuation | double spaces, a space before punctuation, a missing space after a comma, `,,` |
| Style       | wordy phrases (`in order to` → `to`, `due to the fact that` → `because`), `!!!` |
| Clarity     | passive voice, sentences over 35 words |

The built-in rules are deliberately conservative to avoid false alarms. For
subject–verb agreement, complex grammar and a complete dictionary, turn on
**Deep check**.

## Use it

Open `index.html` in any browser. That's it. To serve it locally instead:

```sh
npm start        # serves on http://localhost:8080
```

### Host it for free on GitHub Pages

In the repository, go to **Settings → Pages**, choose **Deploy from a branch**,
then select the `main` branch and the `/ (root)` folder. The site appears at
`https://<user>.github.io/grammarhelp/`.

## Deep check and privacy

When **Deep check** is turned on, your text goes to the public LanguageTool API
(`api.languagetool.org`). That API is free but limited to about 20 requests per
minute and 20 KB of text per request. To keep text private and remove the limits,
run your own LanguageTool server:

```sh
docker run -d -p 8010:8010 erikvl87/languagetool
```

Then change `DEFAULT_ENDPOINT` in `src/languagetool.js` to
`http://localhost:8010/v2/check`.

## Development

```
index.html            page shell
src/checker.js        rule-based checker (no dependencies; works in the browser and in Node)
src/languagetool.js   optional LanguageTool API client
src/app.js            editor, highlighting and suggestions UI
src/styles.css        styles (light and dark)
test/                 unit tests (node:test)
```

```sh
npm test
```

To add a rule, write a function in `src/checker.js` that pushes
`{ offset, length, message, category, rule, replacements }` objects. Then add it
to `RULES` and cover it in `test/checker.test.js`.

## License

MIT
