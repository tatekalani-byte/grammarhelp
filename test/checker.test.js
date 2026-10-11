const test = require('node:test');
const assert = require('node:assert/strict');
const { check, applyReplacement, stats, matchCase } = require('../src/checker.js');

function rules(text) {
  return check(text).map((i) => i.rule);
}

function fixAll(text) {
  // Apply first suggestion of every fixable issue, right-to-left so offsets stay valid.
  const issues = check(text).filter((i) => i.replacements.length && i.rule !== 'LONG_SENTENCE');
  for (const issue of issues.sort((a, b) => b.offset - a.offset)) {
    text = applyReplacement(text, issue, issue.replacements[0]);
  }
  return text;
}

test('clean text has no issues', () => {
  assert.deepEqual(check('This is a clean sentence. It has an apple in it.'), []);
});

test('spelling', () => {
  assert.equal(fixAll('I definately recieved it.'), 'I definitely received it.');
  assert.equal(fixAll('Teh end.'), 'The end.');
});

test('repeated words', () => {
  assert.equal(fixAll('This is the the end.'), 'This is the end.');
  assert.deepEqual(rules('He said that that was fine.'), []);
});

test('a / an', () => {
  assert.equal(fixAll('She ate a apple and an banana.'), 'She ate an apple and a banana.');
  assert.deepEqual(rules('It took an hour at a university.'), []);
  assert.deepEqual(rules('He is a European and an honest man.'), []);
  assert.deepEqual(rules('Open a URL from an FBI agent.'), []);
});

test('lowercase i', () => {
  assert.equal(fixAll('Yesterday i think i\'m right.'), 'Yesterday I think I\'m right.');
  assert.deepEqual(rules('See section (i) and i.e. examples.').filter((r) => r === 'LOWERCASE_I').length <= 1, true);
});

test('sentence capitalization', () => {
  assert.equal(fixAll('hello there. how are you?'), 'Hello there. How are you?');
  assert.deepEqual(rules('Use tools, e.g. hammers. Also Dr. smith.'), []);
  assert.deepEqual(rules('Wait... what happened?'), []);
});

test('whitespace and punctuation', () => {
  assert.equal(fixAll('Hello  world , how are you?'), 'Hello world, how are you?');
  assert.equal(fixAll('Apples,pears and plums.'), 'Apples, pears and plums.');
  assert.deepEqual(rules('It costs 0.5 dollars... maybe.'), []);
});

test('confusions', () => {
  assert.equal(fixAll('I could of done better then him.'), 'I could have done better than him.');
  assert.equal(fixAll('Your welcome.'), "You're welcome.");
  assert.equal(fixAll('Its a nice day.'), "It's a nice day.");
  assert.equal(fixAll('Their is a problem.'), 'There is a problem.');
  assert.equal(fixAll('That is to much.'), 'That is too much.');
  assert.equal(fixAll("Don't loose it."), "Don't lose it.");
  assert.equal(fixAll('We use alot of tools.'), 'We use a lot of tools.');
  assert.deepEqual(rules('The dog wagged its tail.'), []);
  assert.deepEqual(rules('I went to bed.'), []);
});

test('wordiness', () => {
  assert.equal(fixAll('In order to win, we trained.'), 'To win, we trained.');
  assert.equal(fixAll('We left due to the fact that it rained.'), 'We left because it rained.');
});

test('passive voice is flagged without a fix', () => {
  const issues = check('The ball was thrown by the boy.');
  assert.equal(issues.length, 1);
  assert.equal(issues[0].rule, 'PASSIVE_VOICE');
  assert.deepEqual(issues[0].replacements, []);
  assert.deepEqual(rules('I was tired and she was often late.'), []);
});

test('long sentences', () => {
  const long = Array.from({ length: 40 }, () => 'word').join(' ') + '.';
  assert.ok(rules('Word ' + long).includes('LONG_SENTENCE'));
});

test('issues never overlap except sentence-length hints', () => {
  const issues = check('i could of definately done it it better then them,they said  .')
    .filter((i) => i.rule !== 'LONG_SENTENCE');
  for (let a = 0; a < issues.length; a++) {
    for (let b = a + 1; b < issues.length; b++) {
      const x = issues[a], y = issues[b];
      assert.ok(x.offset + x.length <= y.offset || y.offset + y.length <= x.offset,
        `overlap: ${x.rule} / ${y.rule}`);
    }
  }
});

test('matchCase', () => {
  assert.equal(matchCase('Teh', 'the'), 'The');
  assert.equal(matchCase('TEH', 'the'), 'THE');
  assert.equal(matchCase('teh', 'the'), 'the');
});

test('stats', () => {
  const s = stats('The cat sat. The dog ran.');
  assert.equal(s.words, 6);
  assert.equal(s.sentences, 2);
  assert.ok(s.readability > 80);
  assert.equal(stats('').readability, null);
});
