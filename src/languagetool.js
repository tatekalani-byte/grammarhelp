/*
 * Optional deeper checking via LanguageTool (https://languagetool.org), an
 * open-source grammar engine. The public API is free (rate-limited to ~20
 * requests/minute and 20 KB per request). Text is sent to the server, so the
 * app only calls this when the user turns it on.
 *
 * You can point this at a self-hosted server (docker run -p 8010:8010
 * erikvl87/languagetool) to keep text private and remove the rate limit.
 */
(function (root) {
  'use strict';

  const DEFAULT_ENDPOINT = 'https://api.languagetool.org/v2/check';
  const MAX_CHARS = 20000;

  const CATEGORY_BY_ISSUE_TYPE = {
    misspelling: 'spelling',
    grammar: 'grammar',
    typographical: 'punctuation',
    whitespace: 'punctuation',
    style: 'style',
    'locale-violation': 'spelling',
    duplication: 'grammar',
    inconsistency: 'style',
  };

  async function check(text, { language = 'auto', endpoint = DEFAULT_ENDPOINT, signal } = {}) {
    if (!text.trim()) return [];
    const body = new URLSearchParams({
      text: text.slice(0, MAX_CHARS),
      language,
      enabledOnly: 'false',
    });
    if (language === 'auto') body.set('preferredVariants', 'en-US');

    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
      body,
      signal,
    });
    if (res.status === 429) throw new Error('LanguageTool rate limit reached — try again in a minute.');
    if (!res.ok) throw new Error(`LanguageTool error (${res.status}).`);
    const data = await res.json();

    return (data.matches || []).map((m) => ({
      offset: m.offset,
      length: m.length,
      message: m.message,
      category: CATEGORY_BY_ISSUE_TYPE[m.rule && m.rule.issueType] || 'clarity',
      rule: 'LT_' + (m.rule ? m.rule.id : 'UNKNOWN'),
      replacements: (m.replacements || []).slice(0, 5).map((r) => r.value),
      source: 'LanguageTool',
    }));
  }

  root.LanguageToolClient = { check, DEFAULT_ENDPOINT, MAX_CHARS };
})(typeof self !== 'undefined' ? self : this);
