// Runs the page expressions shipped in devin-fetch.sh (DONE_EXPR, EXPAND_EXPR,
// FRESHNESS_EXPR) against fake pages, so the test exercises the script's own
// code and not a copy of it. Run: node devin-fetch.test.mjs
import {readFileSync} from 'fs';
import {dirname, join} from 'path';
import {fileURLToPath} from 'url';

const sh = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'devin-fetch.sh'), 'utf8');
function expr(name) {
  const m = sh.match(new RegExp(`^${name}='([\\s\\S]*?)'\\n`, 'm'));
  if (!m) { console.error(`could not extract ${name} from devin-fetch.sh`); process.exit(2); }
  return m[1];
}

// A fake page: innerText plus buttons with a label, an optional aria-expanded
// value, and a click log.
function page(text, buttons = [], flags = {}) {
  const clicked = [];
  const els = buttons.map(([label, expanded]) => ({
    textContent: label,
    getAttribute: (n) => (n === 'aria-expanded' ? (expanded ?? null) : null),
    click: () => clicked.push(label),
  }));
  globalThis.window = {...flags};
  globalThis.document = {body: {innerText: text}, querySelectorAll: () => els};
  return clicked;
}

let bad = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) bad++;
  console.log(`${ok ? 'ok  ' : 'BAD '} ${name}${ok ? '' : `: want ${JSON.stringify(want)}, got ${JSON.stringify(got)}`}`);
}

const DONE = expr('DONE_EXPR');
const H = "Devin's analysis";
const polled = {__devinFetchViewClicked: true, __devinFetchNewClicked: true};
const doneCases = [
  ['finished page: heading, flags, settled rail', `${H}\n2 Flags\nChecks\n9/9`, true],
  ['finished page: per-category counts', `${H}\n0 Vulnerabilities\n1 Bug\n1 Flag`, true],
  ['older heading spelling', "Devin's AI analysis\n2 Flags\nChecks 22/22", true],
  ['transition card: Analysis complete', `${H}\nAnalysis complete`, true],
  ['settled rail before the banner renders', `${H}\nChecks 22/22`, true],
  ['failed checks still carry a verdict', `${H}\n1 Flag\n2 checks failed`, true],
  ['no flags with the all-passed banner', `${H}\nNo flags\nAll checks passed`, true],
  ['partial rail with the verdict behind View results', `${H}\nView results\nChecks 12/22`, false],
  ['partial rail while diffs load', `${H}\nChecks 3/22\nLoading diffs…`, false],
  ['still generating', `${H}\nGenerating...\nNo flags`, false],
  ['in progress, no result', `PR analysis in progress\n${H}`, false],
  ['partial rail only, no heading', 'Checks 12/22', false],
];
for (const [name, text, want] of doneCases) { page(text, [], polled); check(`done: ${name}`, eval(DONE), want); }

let clicks = page(`${H}\n2 Flags\nChecks 9/9`, [['New analysis 2'], ['View results']]);
check('done: first poll opens the newest analysis and waits', [eval(DONE), clicks], [false, ['New analysis 2']]);
clicks = page(`${H}\nAnalysis complete`, [['New analysis 2'], ['View results']], {__devinFetchNewClicked: true});
check('done: next poll clicks View results once and waits', [eval(DONE), clicks], [false, ['View results']]);

const EXPAND = expr('EXPAND_EXPR');
clicks = page('', [['1 Bug', 'true'], ['1 Flag', 'false'], ['0 Vulnerabilities', 'true'], ['2 Flags'], ['Post to GitHub'], ['Copy'], ['Read more']]);
eval(EXPAND);
check('expand: clicks closed and legacy headers only, never Post to GitHub', clicks, ['1 Flag', '2 Flags', 'Read more']);

const FRESH = expr('FRESHNESS_EXPR');
const tab = (rows) => `Description\nDiscussion\n1\nCommits\n${rows.length}\n` + rows.map(([title, sha, current]) =>
  `${title}\n${current ? 'Current\n•\n' : ''}5 minutes ago\n•\nwriter\n${current ? '•\n' : ''}${sha}\n${current ? 'Analysis complete\n' : ''}`).join('');
page(tab([['Merge main', '4499555', true], ['Fix timeout', '2af0bda'], ['Add test', '8f74de2']]));
check('freshness: analysed commit is the newest', eval(FRESH), 'Analysis is up to date (4499555)');
page(tab([['Merge main', '4499555'], ['Fix timeout', '2af0bda', true], ['Add test', '8f74de2']]));
check('freshness: analysed commit is older than the head', eval(FRESH), 'Analysis is behind the head commit (analysed 2af0bda, head 4499555)');
page(`${H}\nCommits\n3\n${H}\nNarrative text`);
check('freshness: tab did not open, no Current marker', eval(FRESH), 'unknown');
page(`${H}\n1 Flag`);
check('freshness: no Commits tab', eval(FRESH), 'unknown');

console.log(`\n${bad} failing`);
process.exit(bad ? 1 : 0);
