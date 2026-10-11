/*
 * GrammarHelp local checker.
 *
 * A dependency-free, rule-based grammar/spelling/style checker that runs
 * entirely in the browser (or in Node for tests). Nothing leaves the device.
 *
 * check(text, { dialect: 'en-US' | 'en-GB' | ... }) -> Issue[]
 *   Issue = {
 *     offset, length,        // range in `text`
 *     message,               // human-readable explanation
 *     category,              // spelling | grammar | punctuation | style | clarity
 *     rule,                  // stable rule id
 *     replacements: string[] // suggested fixes (may be empty)
 *   }
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.GrammarChecker = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Data
  // ---------------------------------------------------------------------------

  const MISSPELLINGS = {
    accomodate: 'accommodate', acheive: 'achieve', accross: 'across',
    adress: 'address', agressive: 'aggressive', alot: 'a lot',
    apparantly: 'apparently', arguement: 'argument', basicly: 'basically',
    becuase: 'because', becasue: 'because', begining: 'beginning',
    beleive: 'believe', belive: 'believe', buisness: 'business',
    calender: 'calendar', carribean: 'Caribbean', cemetary: 'cemetery',
    collegue: 'colleague', comming: 'coming', commitee: 'committee',
    completly: 'completely', concious: 'conscious', curiousity: 'curiosity',
    definately: 'definitely', definatly: 'definitely', dissapoint: 'disappoint',
    embarass: 'embarrass', enviroment: 'environment', existance: 'existence',
    familar: 'familiar', finaly: 'finally', foriegn: 'foreign',
    foward: 'forward', freind: 'friend', fourty: 'forty', gaurd: 'guard',
    goverment: 'government', grammer: 'grammar', happend: 'happened',
    harrass: 'harass', immediatly: 'immediately', independant: 'independent',
    interupt: 'interrupt', irregardless: 'regardless', knowlege: 'knowledge',
    libary: 'library', lisence: 'license', maintainance: 'maintenance',
    millenium: 'millennium', mispell: 'misspell', neccessary: 'necessary',
    necessery: 'necessary', noticable: 'noticeable', occassion: 'occasion',
    occured: 'occurred', occurence: 'occurrence', occurrance: 'occurrence',
    paralell: 'parallel', persistant: 'persistent', persue: 'pursue',
    posession: 'possession', posible: 'possible', prefered: 'preferred',
    privelege: 'privilege', probaly: 'probably', publically: 'publicly',
    realy: 'really', recieve: 'receive', recieved: 'received',
    reccomend: 'recommend', recomend: 'recommend', refered: 'referred',
    relevent: 'relevant', religous: 'religious', remeber: 'remember',
    resistence: 'resistance', rythm: 'rhythm', seperate: 'separate',
    seperately: 'separately', sieze: 'seize', similiar: 'similar',
    sincerly: 'sincerely', speach: 'speech', succesful: 'successful',
    sucessful: 'successful', suprise: 'surprise', tatoo: 'tattoo',
    teh: 'the', tendancy: 'tendency', therefor: 'therefore', thier: 'their',
    threshhold: 'threshold', tommorow: 'tomorrow', tommorrow: 'tomorrow',
    tounge: 'tongue', truely: 'truly', twelth: 'twelfth', untill: 'until',
    usefull: 'useful', vaccuum: 'vacuum', wich: 'which', wierd: 'weird',
    whereever: 'wherever', writting: 'writing', wether: 'whether',
    beautifull: 'beautiful', acommodate: 'accommodate', adn: 'and',
    hte: 'the', taht: 'that', waht: 'what', recieving: 'receiving',
    occuring: 'occurring', begginning: 'beginning',
  };

  // Words starting with a vowel letter but a consonant sound -> "a".
  const A_EXCEPTIONS = /^(uni|use|usu|uti|ure|uri|uro|eu|ewe|one|once|ubiq|ufo|uk\b|us\b)/i;
  // Words starting with a consonant letter but a vowel sound -> "an".
  const AN_EXCEPTIONS = /^(hour|honest|honou?r|heir|herb\b)/i;

  const WORDY = [
    ['in order to', ['to']],
    ['due to the fact that', ['because']],
    ['owing to the fact that', ['because']],
    ['in light of the fact that', ['because']],
    ['despite the fact that', ['although']],
    ['at this point in time', ['now']],
    ['at the present time', ['now', 'currently']],
    ['in the event that', ['if']],
    ['for the purpose of', ['to', 'for']],
    ['a large number of', ['many']],
    ['a majority of', ['most']],
    ['in the near future', ['soon']],
    ['has the ability to', ['can']],
    ['have the ability to', ['can']],
    ['is able to', ['can']],
    ['in spite of the fact that', ['although']],
    ['with regard to', ['about', 'regarding']],
    ['with regards to', ['about', 'regarding']],
    ['in regards to', ['about', 'regarding']],
    ['each and every', ['every', 'each']],
    ['first and foremost', ['first']],
    ['basic fundamentals', ['fundamentals']],
    ['end result', ['result']],
    ['past history', ['history']],
    ['free gift', ['gift']],
    ['very unique', ['unique']],
    ['absolutely essential', ['essential']],
    ['completely finished', ['finished']],
    ['the reason why is because', ['because']],
    ['the reason is because', ['the reason is that', 'because']],
  ];

  // Confusable pairs detected by context. Each entry: regex (global, case-
  // insensitive), the capture group index to replace, replacement fn, message.
  const CONFUSIONS = [
    {
      rule: 'COULD_OF',
      re: /\b(could|should|would|must|might|may)\s+(of)\b/gi,
      group: 2, fix: () => 'have',
      message: 'Use "have" instead of "of" after a modal verb.',
    },
    {
      rule: 'THEN_THAN',
      re: /\b(more|less|better|worse|rather|other|greater|fewer|larger|smaller|faster|slower|higher|lower|bigger|older|younger|longer|shorter|easier|harder)\s+(then)\b/gi,
      group: 2, fix: () => 'than',
      message: 'Use "than" for comparisons.',
    },
    {
      rule: 'YOUR_YOURE',
      re: /\b(your)\s+(welcome|a|an|the|not|going|being|so|very|right|wrong|correct|probably|definitely|always|never)\b/gi,
      group: 1, fix: () => "you're",
      message: 'Did you mean "you\'re" (you are)?',
    },
    {
      rule: 'ITS_ITS',
      re: /\b(its)\s+(a|an|the|been|not|going|time|important|true|likely|possible|clear|obvious|okay|ok|fine|hard|easy|so|very|just|really|my|your|our|been)\b/gi,
      group: 1, fix: () => "it's",
      message: 'Did you mean "it\'s" (it is / it has)?',
    },
    {
      rule: 'THEIR_THERE',
      re: /\b(their|they're)\s+(is|are|was|were|will be|has been|have been)\b/gi,
      group: 1, fix: () => 'there',
      message: 'Did you mean "there"?',
    },
    {
      rule: 'TO_TOO',
      re: /\b(to)\s+(much|many|late|early|soon|bad|big|small|long|often|far|hard)\b(?!\s+(?:of|for)\b)/gi,
      group: 1, fix: () => 'too',
      message: 'Did you mean "too" (excessively)?',
      // "to" after verbs like "go to bad places" is rare; restrict to sentence-ish
      // contexts by skipping when preceded by a verb that takes "to".
      skipBefore: /\b(go|went|going|come|came|back|up|down|close|next|due|moved?|turned?|listen|talk|speak|similar|compared|according)\s*$/i,
    },
    {
      rule: 'LOOSE_LOSE',
      re: /\b(to|will|can|could|might|may|don't|didn't|not|never)\s+(loose)\b/gi,
      group: 2, fix: () => 'lose',
      message: 'Did you mean "lose" (to misplace or fail to win)?',
    },
    {
      rule: 'WHO_WHOSE',
      re: /\b(who's)\s+(car|house|book|idea|job|name|turn|fault|phone|dog|cat|responsibility)\b/gi,
      group: 1, fix: () => 'whose',
      message: 'Use "whose" to show possession.',
    },
    {
      rule: 'ALOT',
      re: /\b(alot)\b/gi,
      group: 1, fix: () => 'a lot',
      message: '"A lot" is two words.',
      category: 'spelling',
    },
    {
      rule: 'SUPPOSE_TO',
      re: /\b(suppose|use)\s+(to)\b/gi,
      group: 1, fix: (w) => w.toLowerCase() === 'suppose' ? 'supposed' : 'used',
      message: 'Did you mean "supposed to" / "used to"?',
      skipBefore: /\b(I|we|you|they|to|would|will|can|could|should|might|may|don't|didn't|let's|the|a|no|of|for|in|make|good|any)\s*$/i,
    },
  ];

  const PASSIVE_EXCLUDE = new Set([
    'tired', 'interested', 'excited', 'bored', 'scared', 'worried', 'married',
    'concerned', 'pleased', 'satisfied', 'surprised', 'supposed', 'used',
    'based', 'located', 'involved', 'needed', 'related', 'allowed', 'required',
    'determined', 'prepared', 'qualified', 'experienced', 'talented', 'ashamed',
    'confused', 'amazed', 'embarrassed', 'exhausted', 'disappointed', 'need',
    'red', 'bed', 'shed', 'sled', 'shred', 'wed', 'fed', 'led', 'bred', 'sped',
    'naked', 'wicked', 'sacred', 'hundred', 'kindred', 'rugged', 'ragged',
  ]);

  const IRREGULAR_PARTICIPLES = new Set([
    'taken', 'written', 'given', 'broken', 'chosen', 'driven', 'eaten',
    'forgotten', 'hidden', 'known', 'seen', 'shown', 'spoken', 'stolen',
    'thrown', 'beaten', 'bitten', 'done', 'drawn', 'grown', 'ridden', 'shaken',
    'sworn', 'torn', 'worn', 'woken', 'proven', 'forgiven', 'frozen', 'made',
    'built', 'sent', 'paid', 'told', 'sold', 'held', 'caught', 'taught',
    'bought', 'brought', 'found', 'kept', 'left', 'lost', 'meant', 'put',
    'read', 'set', 'spent', 'struck', 'understood', 'won', 'hit', 'cut',
  ]);

  const ABBREVIATIONS = new Set([
    'e.g', 'i.e', 'etc', 'vs', 'mr', 'mrs', 'ms', 'dr', 'prof', 'sr', 'jr',
    'st', 'no', 'fig', 'approx', 'inc', 'ltd', 'co', 'jan', 'feb', 'mar',
    'apr', 'jun', 'jul', 'aug', 'sep', 'sept', 'oct', 'nov', 'dec', 'p', 'pp',
    'vol', 'ed', 'al', 'cf', 'a.m', 'p.m', 'u.s',
  ]);

  const LONG_SENTENCE_WORDS = 35;

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function matchCase(original, replacement) {
    if (!original || !replacement) return replacement;
    if (original.length > 1 && original === original.toUpperCase() && /[A-Z]/.test(original)) {
      return replacement.toUpperCase();
    }
    if (original[0] === original[0].toUpperCase() && original[0] !== original[0].toLowerCase()) {
      return replacement[0].toUpperCase() + replacement.slice(1);
    }
    return replacement;
  }

  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  // Offset of capture group `g` within a regex match. Assumes groups appear in
  // order and are separated only by the literal text in between (true for all
  // rules here, which use "\s+" between groups).
  function groupOffset(match, g) {
    let pos = match.index;
    let searchFrom = 0;
    for (let i = 1; i <= g; i++) {
      const idx = match[0].indexOf(match[i], searchFrom);
      if (i === g) return pos + idx;
      searchFrom = idx + match[i].length;
    }
    return pos;
  }

  // ---------------------------------------------------------------------------
  // Rules
  // ---------------------------------------------------------------------------

  function spelling(text, out) {
    const re = /\b[A-Za-z]+\b/g;
    let m;
    while ((m = re.exec(text))) {
      const lower = m[0].toLowerCase();
      if (Object.prototype.hasOwnProperty.call(MISSPELLINGS, lower) && lower !== 'alot') {
        out.push({
          offset: m.index, length: m[0].length,
          message: `Possible spelling mistake: "${m[0]}".`,
          category: 'spelling', rule: 'MISSPELLING',
          replacements: [matchCase(m[0], MISSPELLINGS[lower])],
        });
      }
    }
  }

  function repeatedWords(text, out) {
    const re = /\b([A-Za-z']+)(\s+)(\1)\b/gi;
    let m;
    while ((m = re.exec(text))) {
      const w = m[1].toLowerCase();
      if (w === 'had' || w === 'that') continue; // "had had", "that that" can be valid
      out.push({
        offset: m.index, length: m[0].length,
        message: `The word "${m[1]}" is repeated.`,
        category: 'grammar', rule: 'REPEATED_WORD',
        replacements: [m[1]],
      });
      re.lastIndex = m.index + m[1].length; // allow "the the the" to report twice
    }
  }

  function articles(text, out) {
    const re = /\b(a|an)\s+([A-Za-z][\w-]*)/gi;
    let m;
    while ((m = re.exec(text))) {
      const article = m[1];
      const word = m[2];
      // Skip acronyms/initialisms ("an FBI agent", "a URL") — pronunciation varies.
      if (word.length > 1 && word === word.toUpperCase()) continue;
      // Skip "a" used as a letter/label ("Plan A an option" is too rare to care).
      const startsVowel = /^[aeiou]/i.test(word);
      let wantsAn = startsVowel;
      if (startsVowel && A_EXCEPTIONS.test(word)) wantsAn = false;
      if (!startsVowel && AN_EXCEPTIONS.test(word)) wantsAn = true;
      const isAn = article.toLowerCase() === 'an';
      if (wantsAn !== isAn) {
        const fix = matchCase(article, wantsAn ? 'an' : 'a');
        out.push({
          offset: m.index, length: article.length,
          message: `Use "${fix.toLowerCase()}" before "${word}".`,
          category: 'grammar', rule: 'A_AN',
          replacements: [fix],
        });
      }
    }
  }

  function lowercaseI(text, out) {
    // Skip list markers "(i)" and the abbreviation "i.e.".
    const re = /(^|[^\w'’(-])(i)(?=$|[^\w.)-]|\.(?![a-z])|['’](?:m|ve|ll|d)\b)/g;
    let m;
    while ((m = re.exec(text))) {
      out.push({
        offset: m.index + m[1].length, length: 1,
        message: 'The pronoun "I" is always capitalized.',
        category: 'grammar', rule: 'LOWERCASE_I',
        replacements: ['I'],
      });
    }
  }

  function sentenceCapitalization(text, out) {
    // After sentence-ending punctuation.
    const midRe = /([.!?])(["')\]]?)(\s+)([a-z])/g;
    let m;
    // Start of text and start of each paragraph.
    const first = /^\s*([a-z])/.exec(text);
    if (first) {
      const off = first.index + first[0].length - 1;
      out.push(capIssue(off, first[1]));
    }
    const paraRe = /\n\s*\n\s*([a-z])/g;
    while ((m = paraRe.exec(text))) {
      out.push(capIssue(m.index + m[0].length - 1, m[1]));
    }
    while ((m = midRe.exec(text))) {
      if (m[1] === '.') {
        // Look back for an abbreviation or an ellipsis.
        const before = text.slice(Math.max(0, m.index - 12), m.index);
        const tok = /([A-Za-z.]+)$/.exec(before);
        if (tok && ABBREVIATIONS.has(tok[1].toLowerCase().replace(/^\.+/, ''))) continue;
        if (tok && /^[A-Za-z]$/.test(tok[1])) continue; // initials: "J. smith" (rare), "a. b."
        if (before.endsWith('..')) continue; // ellipsis
        if (/\d$/.test(before)) continue; // "v1. something" / numbered lists
      }
      const off = m.index + m[0].length - 1;
      out.push(capIssue(off, m[4]));
    }
  }

  function capIssue(offset, ch) {
    return {
      offset, length: 1,
      message: 'Sentences should start with a capital letter.',
      category: 'grammar', rule: 'SENTENCE_CAPITAL',
      replacements: [ch.toUpperCase()],
    };
  }

  function whitespaceAndPunctuation(text, out) {
    let m;
    // Multiple spaces between words.
    const multi = /(\S)( {2,})(?=\S)/g;
    while ((m = multi.exec(text))) {
      out.push({
        offset: m.index + 1, length: m[2].length,
        message: 'Remove the extra spaces.',
        category: 'punctuation', rule: 'DOUBLE_SPACE',
        replacements: [' '],
      });
    }
    // Space before punctuation: "word ," / "word ." (but not ".5" or "...").
    const before = /([A-Za-z0-9)])( +)([,;:!?]|\.(?![.\d]))/g;
    while ((m = before.exec(text))) {
      out.push({
        offset: m.index + m[1].length, length: m[2].length,
        message: `Remove the space before "${m[3]}".`,
        category: 'punctuation', rule: 'SPACE_BEFORE_PUNCT',
        replacements: [''],
      });
    }
    // Missing space after comma / semicolon: "word,word".
    const after = /([A-Za-z])([,;])(?=[A-Za-z])/g;
    while ((m = after.exec(text))) {
      out.push({
        offset: m.index + 1, length: 1,
        message: `Add a space after "${m[2]}".`,
        category: 'punctuation', rule: 'SPACE_AFTER_PUNCT',
        replacements: [m[2] + ' '],
      });
    }
    // Repeated punctuation: ",," or "!!!" / "??" (style).
    const rep = /([,;:])\1+|([!?]){2,}/g;
    while ((m = rep.exec(text))) {
      const ch = m[1] || m[2];
      out.push({
        offset: m.index, length: m[0].length,
        message: ch === ',' || ch === ';' || ch === ':'
          ? `Duplicate "${ch}".`
          : 'Repeated punctuation can look unprofessional.',
        category: ch === '!' || ch === '?' ? 'style' : 'punctuation',
        rule: 'REPEATED_PUNCT',
        replacements: [ch],
      });
    }
  }

  function confusions(text, out) {
    for (const c of CONFUSIONS) {
      c.re.lastIndex = 0;
      let m;
      while ((m = c.re.exec(text))) {
        if (c.skipBefore && c.skipBefore.test(text.slice(Math.max(0, m.index - 30), m.index))) continue;
        const target = m[c.group];
        const offset = groupOffset(m, c.group);
        out.push({
          offset, length: target.length,
          message: c.message,
          category: c.category || 'grammar', rule: c.rule,
          replacements: [matchCase(target, c.fix(target))],
        });
      }
    }
  }

  function wordiness(text, out) {
    for (const [phrase, subs] of WORDY) {
      const re = new RegExp('\\b' + escapeRegExp(phrase).replace(/ /g, '\\s+') + '\\b', 'gi');
      let m;
      while ((m = re.exec(text))) {
        out.push({
          offset: m.index, length: m[0].length,
          message: `"${m[0]}" is wordy. Consider a shorter phrase.`,
          category: 'style', rule: 'WORDY',
          replacements: subs.map((s) => matchCase(m[0], s)),
        });
      }
    }
  }

  function passiveVoice(text, out) {
    const re = /\b(am|is|are|was|were|be|been|being)\s+([a-z]+)\b/gi;
    let m;
    while ((m = re.exec(text))) {
      const participle = m[2].toLowerCase();
      const regular = /[a-z]{2,}ed$/.test(participle) && !PASSIVE_EXCLUDE.has(participle);
      if (!regular && !IRREGULAR_PARTICIPLES.has(participle)) continue;
      out.push({
        offset: m.index, length: m[0].length,
        message: 'Possible passive voice. Active voice is often clearer.',
        category: 'clarity', rule: 'PASSIVE_VOICE',
        replacements: [],
      });
    }
  }

  function longSentences(text, out) {
    const re = /[^.!?\n]+[.!?]*/g;
    let m;
    while ((m = re.exec(text))) {
      const words = m[0].trim().split(/\s+/).filter(Boolean);
      if (words.length > LONG_SENTENCE_WORDS) {
        const lead = m[0].length - m[0].trimStart().length;
        out.push({
          offset: m.index + lead, length: m[0].trim().length,
          message: `This sentence has ${words.length} words. Consider splitting it up.`,
          category: 'clarity', rule: 'LONG_SENTENCE',
          replacements: [],
        });
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Premium-style suggestions (conciseness, word choice, delivery)
  // ---------------------------------------------------------------------------

  // Verb forms: [base, 3rd person, past, -ing, past participle].
  const VERB_PHRASES = [
    { verb: ['make', 'makes', 'made', 'making', 'made'], rest: 'a\\s+decision',
      to: [['decide', 'decides', 'decided', 'deciding', 'decided']] },
    { verb: ['come', 'comes', 'came', 'coming', 'come'],
      rest: 'to\\s+(more\\s+of\\s+an|a\\s+better|an)\\s+understanding(?:\\s+of)?',
      to: [['understand', 'understands', 'understood', 'understanding', 'understood']],
      better: (m) => !/^an$/i.test(m[2]) },
    { verb: ['take', 'takes', 'took', 'taking', 'taken'], rest: 'into\\s+consideration',
      to: [['consider', 'considers', 'considered', 'considering', 'considered']] },
    { verb: ['give', 'gives', 'gave', 'giving', 'given'], rest: 'an\\s+explanation(?:\\s+(?:of|for))?',
      to: [['explain', 'explains', 'explained', 'explaining', 'explained']] },
    { verb: ['reach', 'reaches', 'reached', 'reaching', 'reached'], rest: 'a\\s+conclusion',
      to: [['conclude', 'concludes', 'concluded', 'concluding', 'concluded']] },
    { verb: ['make', 'makes', 'made', 'making', 'made'], rest: 'an\\s+attempt',
      to: [['try', 'tries', 'tried', 'trying', 'tried']] },
    { verb: ['conduct', 'conducts', 'conducted', 'conducting', 'conducted'],
      rest: 'an\\s+investigation(?:\\s+(?:into|of))?',
      to: [['investigate', 'investigates', 'investigated', 'investigating', 'investigated']] },
    { verb: ['have', 'has', 'had', 'having', 'had'], rest: 'a\\s+discussion(?:\\s+(?:about|of))?',
      to: [['discuss', 'discusses', 'discussed', 'discussing', 'discussed']] },
    { verb: ['provide', 'provides', 'provided', 'providing', 'provided'], rest: 'assistance(?:\\s+to)?',
      to: [['help', 'helps', 'helped', 'helping', 'helped']] },
    { verb: ['get', 'gets', 'got', 'getting', 'gotten'], rest: 'good\\s+at', category: 'style',
      rule: 'INFORMAL', message: '"Get good at" is informal. Try a more precise phrase.',
      to: [['become', 'becomes', 'became', 'becoming', 'become'], ['excel', 'excels', 'excelled', 'excelling', 'excelled']],
      suffix: [' skilled at', ' at'] },
  ];

  function verbPhrases(text, out) {
    for (const vp of VERB_PHRASES) {
      const re = new RegExp('\\b(' + vp.verb.join('|') + ')\\s+(?:' + vp.rest + ')\\b', 'gi');
      let m;
      while ((m = re.exec(text))) {
        const surface = m[1].toLowerCase();
        const afterHave = /\b(have|has|had|having)\s+$/i.test(text.slice(Math.max(0, m.index - 10), m.index));
        let idx = afterHave ? 4 : vp.verb.indexOf(surface);
        if (idx < 0) idx = 0;
        const prefix = vp.better && vp.better(m) ? 'better ' : '';
        const replacements = vp.to.map((forms, i) =>
          matchCase(m[0], prefix + forms[idx] + ((vp.suffix && vp.suffix[i]) || '')));
        out.push({
          offset: m.index, length: m[0].length,
          message: vp.message || `"${m[0]}" is wordy. A single verb is more direct.`,
          category: vp.category || 'style', rule: vp.rule || 'WORDY_VERB',
          replacements,
        });
      }
    }
  }

  const INFORMAL = [
    [/\ba\s+lot\s+of\b/gi, ['many', 'much', 'plenty of'], '"A lot of" is informal. Consider a more precise word.'],
    [/\ba\s+lot\b(?!\s+of\b)/gi, ['a great deal', 'much'], '"A lot" is informal. Consider a more precise phrase.'],
    [/\bgonna\b/gi, ['going to'], '"Gonna" is informal.'],
    [/\bwanna\b/gi, ['want to'], '"Wanna" is informal.'],
    [/\bgotta\b/gi, ['have to'], '"Gotta" is informal.'],
    [/\b(?:kinda|sorta)\b/gi, ['somewhat', 'rather'], 'This is informal. Consider "somewhat".'],
    [/\bgot\s+(?=top\s+\w+)/gi, ['placed in the '], '"Got top …" is informal. Try "placed in the top …".'],
    [/\b(?:was|were)(?=\s+(?:a|an|the)\s+(?:[\w-]+\s+){0,2}?(?:representative|senator|mayor|governor|president|member|manager|captain|director|chair|volunteer|intern|editor|coach|leader)\b)/gi,
      ['served as'], 'For a role or position, "served as" is more engaging than "was".', 'ENGAGING_VERB'],
    [/\b(?:sales|state|customer|service|support|class|student)\s+(reps?)\b/gi, null, '"Rep" is informal. Spell it out.'],
    [/\bwhether\s+or\s+not\b/gi, ['whether'], '"Or not" is usually unnecessary after "whether".', 'WORDY'],
    [/\bon\s+a\s+daily\s+basis\b/gi, ['daily'], 'Wordy phrase.', 'WORDY'],
    [/\bat\s+all\s+times\b/gi, ['always'], 'Wordy phrase.', 'WORDY'],
    [/\buntil\s+such\s+time\s+as\b/gi, ['until'], 'Wordy phrase.', 'WORDY'],
    [/\bso\s+as\s+to\b/gi, ['to'], 'Wordy phrase.', 'WORDY'],
    [/\bin\s+close\s+proximity\s+to\b/gi, ['near'], 'Wordy phrase.', 'WORDY'],
    [/\b(?:is|are)\s+in\s+need\s+of\b/gi, null, 'Wordy phrase.', 'WORDY'],
  ];

  function informal(text, out) {
    for (const [re, subs, message, rule] of INFORMAL) {
      re.lastIndex = 0;
      let m;
      while ((m = re.exec(text))) {
        let replacements = subs;
        let offset = m.index;
        let length = m[0].length;
        if (rule === 'WORDY' && !replacements) {
          replacements = [/^is/i.test(m[0]) ? 'needs' : 'need'];
        } else if (!replacements) {
          // "sales rep(s)": only the abbreviation itself is replaced.
          offset = m.index + m[0].length - m[1].length;
          length = m[1].length;
          replacements = [/s$/i.test(m[1]) ? 'representatives' : 'representative'];
        }
        const original = text.substr(offset, length);
        out.push({
          offset, length, message,
          category: 'style', rule: rule || 'INFORMAL',
          replacements: replacements.map((r) => matchCase(original, r)),
        });
      }
    }
  }

  const STRONGER_WORDS = {
    good: ['excellent', 'great'], bad: ['terrible', 'awful'], big: ['huge', 'enormous'],
    large: ['enormous', 'massive'], small: ['tiny', 'minuscule'], important: ['crucial', 'essential'],
    happy: ['delighted', 'thrilled'], tired: ['exhausted', 'drained'], hungry: ['starving', 'famished'],
    scared: ['terrified', 'petrified'], angry: ['furious', 'livid'], hard: ['difficult', 'grueling'],
    difficult: ['challenging', 'grueling'], easy: ['effortless', 'simple'], fast: ['rapid', 'swift'],
    smart: ['brilliant', 'intelligent'], beautiful: ['gorgeous', 'stunning'],
    interesting: ['fascinating', 'compelling'], cold: ['freezing', 'frigid'], hot: ['scorching', 'sweltering'],
    excited: ['thrilled', 'eager'], loud: ['deafening', 'thunderous'], clean: ['spotless', 'immaculate'],
    dirty: ['filthy', 'grimy'], old: ['ancient', 'aged'], sad: ['heartbroken', 'sorrowful'],
    funny: ['hilarious', 'hysterical'], bright: ['brilliant', 'dazzling'], quiet: ['silent', 'hushed'],
    sure: ['certain', 'confident'], different: ['distinct', 'unusual'], clear: ['obvious', 'evident'],
  };

  function intensifiers(text, out) {
    const re = /\b(very|really|extremely|super)\s+([a-z]+)\b/gi;
    let m;
    while ((m = re.exec(text))) {
      const subs = STRONGER_WORDS[m[2].toLowerCase()];
      if (!subs) continue;
      out.push({
        offset: m.index, length: m[0].length,
        message: `"${m[0]}" is weak. A stronger single word is more vivid.`,
        category: 'style', rule: 'WEAK_INTENSIFIER',
        replacements: subs.map((s) => matchCase(m[0], s)),
      });
    }
  }

  // British spellings flagged when writing American English.
  const US_SPELLINGS = {
    towards: 'toward', afterwards: 'afterward', backwards: 'backward', upwards: 'upward',
    downwards: 'downward', amongst: 'among', whilst: 'while', colour: 'color',
    colours: 'colors', favourite: 'favorite', favourites: 'favorites', honour: 'honor',
    behaviour: 'behavior', neighbour: 'neighbor', neighbours: 'neighbors', humour: 'humor',
    flavour: 'flavor', labour: 'labor', organise: 'organize', organised: 'organized',
    realise: 'realize', realised: 'realized', recognise: 'recognize', recognised: 'recognized',
    apologise: 'apologize', analyse: 'analyze', centre: 'center', theatre: 'theater',
    travelled: 'traveled', travelling: 'traveling', cancelled: 'canceled', defence: 'defense',
    licence: 'license', grey: 'gray', programme: 'program', catalogue: 'catalog',
  };

  function usSpelling(text, out, opts) {
    const dialect = (opts && opts.dialect) || 'en-US';
    if (dialect !== 'en-US' && dialect !== 'auto') return;
    const re = /\b[A-Za-z]+\b/g;
    let m;
    while ((m = re.exec(text))) {
      const us = US_SPELLINGS[m[0].toLowerCase()];
      if (!us) continue;
      out.push({
        offset: m.index, length: m[0].length,
        message: `In American English, "${us}" is preferred over "${m[0].toLowerCase()}".`,
        category: 'spelling', rule: 'US_SPELLING',
        replacements: [matchCase(m[0], us)],
      });
    }
  }

  // "Currently, I'm trying…" — the present progressive already says "now".
  function redundantTimeWords(text, out) {
    const sentenceRe = /[^.!?\n]+[.!?]*/g;
    let s;
    while ((s = sentenceRe.exec(text))) {
      const sentence = s[0];
      if (!/(?:\b(?:am|is|are)|['’](?:m|re|s))\s+(?:(?:currently|presently)\s+)?\w+ing\b/i.test(sentence)) continue;
      const m = /\b(currently|presently|right now)\b,?\s*/i.exec(sentence);
      if (!m) continue;
      const offset = s.index + m.index;
      const atStart = sentence.slice(0, m.index).trim() === '';
      const next = sentence[m.index + m[0].length];
      out.push(atStart && next
        ? {
          offset, length: m[0].length + 1,
          message: `"${m[1]}" is unnecessary here; the verb already shows it's happening now.`,
          category: 'style', rule: 'REDUNDANT_TIME',
          replacements: [next.toUpperCase()],
        }
        : {
          offset, length: m[0].length,
          message: `"${m[1]}" is unnecessary here; the verb already shows it's happening now.`,
          category: 'style', rule: 'REDUNDANT_TIME',
          replacements: [''],
        });
    }
  }

  // "There are many stories that need…" -> "Many stories need…"
  function expletives(text, out) {
    const re = /\b(there)\s+(?:is|are|was|were)\s+((?:[\w'-]+\s+){0,5}?[\w'-]+)\s+(?:that|who|which)\s+(?!(?:I|you|we|they|he|she|it|the|a|an|my|your|our|their|his|her|this|these|those)\b)(?=[a-z])/gi;
    let m;
    while ((m = re.exec(text))) {
      const np = m[2];
      out.push({
        offset: m.index, length: m[0].trimEnd().length,
        message: 'Sentences starting with "There is/are … that" are often wordy. Try making the subject lead.',
        category: 'clarity', rule: 'EXPLETIVE',
        replacements: [/^T/.test(m[1]) ? np[0].toUpperCase() + np.slice(1) : np],
      });
    }
  }

  // Repeating a word within a short span reads as flat; suggest synonyms.
  const SYNONYMS = {
    love: { next: /^\s+\w+ing\b/, subs: ['enjoy', 'relish'] },
    great: { subs: ['excellent', 'outstanding'] },
    good: { subs: ['strong', 'solid'] },
    nice: { subs: ['pleasant', 'lovely'] },
    amazing: { subs: ['incredible', 'remarkable'] },
    awesome: { subs: ['impressive', 'fantastic'] },
    interesting: { subs: ['fascinating', 'intriguing'] },
    important: { subs: ['essential', 'significant'] },
  };
  const REPEAT_WINDOW = 300;

  function overusedWords(text, out) {
    const last = {};
    const re = /\b[A-Za-z]+\b/g;
    let m;
    while ((m = re.exec(text))) {
      const w = m[0].toLowerCase();
      const entry = SYNONYMS[w];
      if (!entry) continue;
      const prev = last[w];
      last[w] = m.index;
      if (prev == null || m.index - prev > REPEAT_WINDOW) continue;
      if (entry.next && !entry.next.test(text.slice(m.index + m[0].length, m.index + m[0].length + 30))) continue;
      out.push({
        offset: m.index, length: m[0].length,
        message: `You've used "${w}" more than once nearby. Try a synonym for variety.`,
        category: 'style', rule: 'REPEATED_NEARBY',
        replacements: entry.subs.map((s) => matchCase(m[0], s)),
      });
    }
  }

  // Three or more sentences in a row starting with the same word.
  function sentenceOpenings(text, out) {
    const re = /(^|[.!?]["')\]]?\s+)([A-Za-z']+)/g;
    let m;
    let prevWord = null;
    let run = 0;
    while ((m = re.exec(text))) {
      const word = m[2].toLowerCase();
      run = word === prevWord ? run + 1 : 1;
      prevWord = word;
      if (run >= 3) {
        out.push({
          offset: m.index + m[1].length, length: m[2].length,
          message: `${run} sentences in a row start with "${m[2]}". Try varying your sentence openings.`,
          category: 'clarity', rule: 'REPETITIVE_OPENING',
          replacements: [],
        });
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  const RULES = [
    spelling, usSpelling, confusions, repeatedWords, articles, lowercaseI,
    sentenceCapitalization, whitespaceAndPunctuation, wordiness, verbPhrases,
    informal, intensifiers, redundantTimeWords, expletives, overusedWords,
    passiveVoice, sentenceOpenings, longSentences,
  ];

  // Lower number wins when two issues overlap.
  const PRIORITY = { spelling: 0, grammar: 1, punctuation: 2, style: 3, clarity: 4 };

  function check(text, options) {
    const opts = options || {};
    const disabled = new Set(opts.disabledRules || []);
    let issues = [];
    for (const rule of RULES) rule(text, issues, opts);
    issues = issues.filter((i) => !disabled.has(i.rule));
    return resolveOverlaps(issues);
  }

  // Remove overlapping issues, keeping the higher-priority / earlier one.
  // Sentence-length hints are allowed to overlap anything since they span a
  // whole sentence and would otherwise hide every other issue in it.
  function resolveOverlaps(issues) {
    const spans = issues.filter((i) => i.rule === 'LONG_SENTENCE');
    const rest = issues
      .filter((i) => i.rule !== 'LONG_SENTENCE')
      .sort((a, b) =>
        (PRIORITY[a.category] - PRIORITY[b.category]) || (a.offset - b.offset) || (b.length - a.length));
    const kept = [];
    for (const issue of rest) {
      const end = issue.offset + issue.length;
      const clash = kept.some((k) => issue.offset < k.offset + k.length && k.offset < end);
      if (!clash) kept.push(issue);
    }
    return kept.concat(spans).sort((a, b) => a.offset - b.offset || a.length - b.length);
  }

  function applyReplacement(text, issue, replacement) {
    return text.slice(0, issue.offset) + replacement + text.slice(issue.offset + issue.length);
  }

  function stats(text) {
    const words = (text.match(/[A-Za-z0-9’']+/g) || []).length;
    const sentences = (text.match(/[^.!?]+[.!?]+/g) || []).length || (words ? 1 : 0);
    const syllables = (text.match(/[A-Za-z]+/g) || []).reduce((n, w) => n + countSyllables(w), 0);
    // Flesch reading ease (0–100, higher = easier).
    const readability = words && sentences
      ? Math.max(0, Math.min(100, Math.round(206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words))))
      : null;
    return {
      characters: text.length,
      words,
      sentences,
      readingTimeMinutes: words / 238,
      readability,
    };
  }

  function countSyllables(word) {
    const w = word.toLowerCase().replace(/e$/, '');
    const groups = w.match(/[aeiouy]+/g);
    return Math.max(1, groups ? groups.length : 0);
  }

  return { check, applyReplacement, stats, resolveOverlaps, matchCase, _MISSPELLINGS: MISSPELLINGS };
});
