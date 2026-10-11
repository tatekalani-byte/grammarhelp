const test = require('node:test');
const assert = require('node:assert/strict');
const { LanguageToolClient } = require('../src/languagetool.js');

test('maps LanguageTool matches to issues', async (t) => {
  let request;
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    request = { url, body: init.body.toString() };
    return {
      ok: true,
      status: 200,
      json: async () => ({
        matches: [{
          message: 'The verb "go" does not agree with "He".',
          offset: 3,
          length: 2,
          replacements: [{ value: 'goes' }, { value: 'went' }],
          rule: { id: 'HE_VERB_AGR', issueType: 'grammar' },
        }],
      }),
    };
  });
  const issues = await LanguageToolClient.check('He go to school.', { language: 'en-US' });
  assert.match(request.body, /language=en-US/);
  assert.deepEqual(issues, [{
    offset: 3, length: 2,
    message: 'The verb "go" does not agree with "He".',
    category: 'grammar', rule: 'LT_HE_VERB_AGR',
    replacements: ['goes', 'went'], source: 'LanguageTool',
  }]);
});

test('reports rate limiting clearly', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, status: 429 }));
  await assert.rejects(LanguageToolClient.check('Hi there.'), /rate limit/);
});

test('skips empty text without a request', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => { throw new Error('should not be called'); });
  assert.deepEqual(await LanguageToolClient.check('   '), []);
  assert.equal(fetch.mock.callCount(), 0);
});
