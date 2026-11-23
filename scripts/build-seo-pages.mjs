#!/usr/bin/env node
/* Builds the static, indexable pages that search engines can read:

     /careers/            all careers, grouped by field
     /careers/<id>/       one page per career
     /exams/              all entrance exams, grouped by stream
     /exams/<id>/         one page per exam
     /degrees/            the degree guides
     /degrees/<slug>/     one page per degree
     sitemap.xml          every URL above plus the home page

   The app itself is one page with hash routes (#explorer, #career/<id>), which Google
   sees as a single URL. These pages give each career, exam and degree its own address.

   Everything comes from data the app already uses, nothing is added by hand:
     - careersData, examsData, EXAM_ALIASES and DEGREE_INFO, read out of index.html
     - data/careers_more.json, data/exams_more.json, data/exams_verified.json
   so after you change any of those, run:   node scripts/build-seo-pages.mjs
   and commit the regenerated folders. Netlify has no build step; it serves these files as they are.

   The pages carry no JavaScript (the site CSP is strict) and link back into the app
   (/#career/<id>, /#exam/<id>) for the live, interactive version. */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SITE = 'https://plan4it.co';
const TODAY = process.env.SEO_BUILD_DATE || new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10); // IST date
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const src = read('index.html');

/* ---------- pull the data literals out of index.html ---------- */
function literal(name) {
  const m = new RegExp('const ' + name + '\\s*=\\s*([\\[{])').exec(src);
  if (!m) throw new Error('Could not find ' + name + ' in index.html');
  const start = m.index + m[0].length - 1;
  let depth = 0, q = null;
  for (let j = start; j < src.length; j++) {
    const c = src[j];
    if (q) { if (c === '\\') { j++; continue; } if (c === q) q = null; continue; }
    if (c === '"' || c === "'" || c === '`') { q = c; continue; }
    if (c === '/' && src[j + 1] === '/') { j = src.indexOf('\n', j); continue; }
    if (c === '/' && src[j + 1] === '*') { j = src.indexOf('*/', j) + 1; continue; }
    if (c === '[' || c === '{') depth++;
    else if (c === ']' || c === '}') { depth--; if (!depth) return vm.runInNewContext('(' + src.slice(start, j + 1) + ')'); }
  }
  throw new Error('Unterminated literal ' + name);
}

const careers = literal('careersData');
const exams = literal('examsData');
const EXAM_ALIASES = literal('EXAM_ALIASES');
const DEGREE_INFO = literal('DEGREE_INFO');

// Same merge the app does in loadMoreData(): add records whose id is not already there.
{
  const have = new Set(careers.map((c) => c.id));
  for (const c of JSON.parse(read('data/careers_more.json'))) if (!have.has(c.id)) careers.push(c);
  const haveX = new Set(exams.map((x) => x.id));
  for (const x of JSON.parse(read('data/exams_more.json'))) if (!haveX.has(x.id)) exams.push(x);
}
// Same as the app's applyVerifiedExams(): official facts override the stored ones.
{
  const map = JSON.parse(read('data/exams_verified.json')).exams || {};
  for (const e of exams) {
    const v = map[e.id]; if (!v) continue;
    if (v.fee) { e.examFee = v.fee; e.feeUnknown = false; }
    for (const k of ['mode', 'duration', 'attempts', 'eligibility', 'body', 'site', 'pattern']) if (v[k]) e[k] = v[k];
    if (v.age) e.ageLimit = v.age;
    e.verifiedLinks = v.links || []; e.verifiedSrc = v.src; e.verifiedOn = v.checked; e.verifiedCycle = v.cycle;
    if (v.last) e.lastCycle = Object.assign({ year: v.cycle }, v.last);
    const nx = v.next;
    if (nx && nx.exam && nx.exam >= TODAY) {
      e.examDate = nx.exam; e.dateStatus = nx.status || 'Official';
      if (nx.short) e.dateShort = nx.short;
      e.regText = nx.regText || e.regText || ''; e.datesUnknown = false; e.info = null;
    }
  }
}

/* ---------- helpers ---------- */
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const PLACEHOLDER = /^\s*$|see (the )?official|not added yet|check (the )?official/i;
const real = (v) => typeof v === 'string' ? !PLACEHOLDER.test(v) : v != null && v !== false;
const GENERIC_COMPETITION = /^Competition changes every year/i;
const clip = (s, n) => { s = String(s || '').replace(/\s+/g, ' ').trim(); if (s.length <= n) return s; const cut = s.slice(0, n - 1); return cut.slice(0, cut.lastIndexOf(' ')).replace(/[,;:.\s]+$/, '') + '…'; };
const httpUrl = (site) => !site ? '' : /^https?:\/\//.test(site) ? site : 'https://' + site.replace(/^\/+/, '');
const hostOf = (u) => { try { return new URL(u).hostname.replace(/^www\./, ''); } catch { return u; } };
const slug = (s) => String(s).toLowerCase().replace(/&/g, ' and ').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmtDate = (iso) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || ''); return m ? `${+m[3]} ${MONTHS[+m[2] - 1]} ${m[1]}` : iso; }; // no locale APIs, so output is identical on every Node version
const jsonLd = (obj) => '<script type="application/ld+json">' + JSON.stringify(obj).replace(/</g, '\\u003c') + '</script>';

const examById = new Map(exams.map((x) => [x.id, x]));
function examsForCareer(c) {
  const out = [];
  for (const n of c.relatedExams || []) {
    let e = exams.find((x) => x.name === n);
    if (!e) { const id = /^GATE\b/.test(n) ? 'gate' : EXAM_ALIASES[n]; e = id && examById.get(id); }
    if (e && !out.includes(e)) out.push(e);
  }
  return out;
}
const careersByExam = new Map();
for (const c of careers) for (const e of examsForCareer(c)) { if (!careersByExam.has(e.id)) careersByExam.set(e.id, []); careersByExam.get(e.id).push(c); }

const DEGREES = Object.entries(DEGREE_INFO).map(([key, d]) => ({ key, slug: slug(key.replace(/\./g, '')), ...d }));
function careersForDegree(key) {
  const k = key.replace(/\./g, '\\.');
  // B.Tech pages also match B.E.; whole-token match so "BA" does not hit "BBA" or "MBA".
  const re = new RegExp('(^|[^A-Za-z.])(' + k + (key === 'B.Tech' ? '|B\\.E\\.?' : '') + ')(?![A-Za-z])');
  return careers.filter((c) => (c.roadmap || []).some((s) => re.test(s)));
}

/* ---------- page shell ---------- */
function page({ urlPath, title, description, h1Eyebrow, body, ld, section, noindex }) {
  const url = SITE + urlPath;
  const nav = [['/careers/', 'Careers', 'careers'], ['/exams/', 'Exams', 'exams'], ['/degrees/', 'Degrees', 'degrees'], ['/#confusedMode', 'Career quiz', '']]
    .map(([h, t, s]) => `<a href="${h}"${s && s === section ? ' aria-current="page"' : ''}>${t}</a>`).join('');
  return `<!DOCTYPE html>
<html lang="en-IN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
<link rel="canonical" href="${url}">
${noindex ? '<meta name="robots" content="noindex, follow">\n' : ''}<meta name="theme-color" content="#101417">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Plan4it.co">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(description)}">
<meta property="og:url" content="${url}">
<meta property="og:image" content="${SITE}/assets/og-image.png">
<meta property="og:locale" content="en_IN">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/assets/favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/seo.css">
${(ld || []).map(jsonLd).join('\n')}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="top"><div class="top-in"><a class="brand" href="/"><img src="/assets/logo-mark-96.png" alt="" width="28" height="28">Plan4it.co</a><nav aria-label="Main">${nav}</nav></div></header>
<main id="main" class="wrap">
${body}
</main>
<footer class="foot"><div class="foot-in">
<p>Fees, cut-offs, dates and eligibility change every year. Always confirm on the official website before you apply or pay. Plan4it.co gives guidance, not a guarantee of admission or a job.</p>
<nav aria-label="Footer"><a href="/">Home</a><a href="/careers/">All careers</a><a href="/exams/">All exams</a><a href="/degrees/">Degrees</a><a href="/#about">About</a><a href="/#privacy">Privacy</a><a href="/#copyright">Terms &amp; copyright</a></nav>
<p>&copy; ${TODAY.slice(0, 4)} Plan4it.co. The content and data on this site may not be copied, scraped or republished without written permission.</p>
</div></footer>
</body>
</html>
`;
}
const crumbs = (items) => {
  const html = '<nav class="crumbs" aria-label="Breadcrumb">' + items.map(([h, t], i) => i === items.length - 1 ? `<span aria-current="page">${esc(t)}</span>` : `<a href="${h}">${esc(t)}</a><span aria-hidden="true">›</span>`).join('') + '</nav>';
  const ld = { '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: items.map(([h, t], i) => ({ '@type': 'ListItem', position: i + 1, name: t, item: SITE + h })) };
  return { html, ld };
};
const fact = (label, value, tag) => real(value) ? `<div><dt>${esc(label)}</dt><dd>${esc(value)}${tag ? `<span class="tag">${esc(tag)}</span>` : ''}</dd></div>` : '';
const list = (arr, cls = 'plain') => arr && arr.length ? `<ul class="${cls}">${arr.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : '';
const linkList = (items) => `<ul class="links">${items.map(([h, t, small]) => `<li><a href="${h}">${esc(t)}${small ? `<small>${esc(small)}</small>` : ''}</a></li>`).join('')}</ul>`;

/* ---------- careers ---------- */
const written = [];
function out(urlPath, html) {
  const file = path.join(ROOT, urlPath, 'index.html');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, html);
}
const sitemap = [{ loc: SITE + '/', pri: '1.0' }];

function careerPage(c) {
  const urlPath = `/careers/${c.id}/`;
  const cr = crumbs([['/', 'Home'], ['/careers/', 'Careers'], [urlPath, c.title]]);
  const ex = examsForCareer(c);
  const similar = careers.filter((x) => x !== c && x.category === c.category).slice(0, 8);
  const extraSkills = (c.skills || []).filter((s) => !(c.skillDetails || []).some((d) => d.name === s));
  const gettingStarted = c.entryYears ? `About ${c.entryYears} years to enter` : '';
  const body = `${cr.html}
<p class="eyebrow">${esc(c.category)} · Career in India</p>
<h1>${esc(c.title)}</h1>
<p class="lede">${esc(c.overview)}</p>
<div class="cta"><a class="btn primary" href="/#career/${esc(c.id)}">Open in Plan4it.co</a><a class="btn" href="/#confusedMode">Take the free career quiz</a></div>
<dl class="facts">
${fact('Typical pay', c.salary, 'approx.')}${fact('Demand', c.demand)}${fact('Difficulty', c.difficulty)}${fact('Getting started', gettingStarted)}${fact('Cost of study', c.costTier)}${fact('Work-life', c.workLife)}${fact('Mobility', c.mobility)}
</dl>
<p class="note">Pay figures are approximate. Real pay depends on city, employer, skills and experience. Check current openings and pay on the National Career Service portal (ncs.gov.in).</p>
${real(c.suitability) ? `<section><h2>Who it suits</h2><p>${esc(c.suitability)}</p></section>` : ''}
${c.roadmap && c.roadmap.length ? `<section><h2>How to become a ${esc(c.title.split(' / ')[0])}</h2><ol class="steps">${c.roadmap.map((s) => `<li>${esc(s)}</li>`).join('')}</ol></section>` : ''}
${(c.skillDetails && c.skillDetails.length) || extraSkills.length ? `<section><h2>Skills you need</h2>
${c.skillDetails && c.skillDetails.length ? `<div class="skills">${c.skillDetails.map((d) => `<div class="skill"><h3>${esc(d.name)}<span class="lvl">${esc([d.level, d.type].filter(Boolean).join(' · '))}</span></h3>${d.why ? `<p>${esc(d.why)}</p>` : ''}${d.resource ? `<p><strong>Where to learn:</strong> ${esc(d.resource)}</p>` : ''}</div>`).join('')}</div>` : ''}
${extraSkills.length ? `<ul class="chips" aria-label="Other skills">${extraSkills.map((s) => `<li>${esc(s)}</li>`).join('')}</ul>` : ''}</section>` : ''}
${c.certifications && c.certifications.length ? `<section><h2>Useful certifications</h2>${list(c.certifications)}</section>` : ''}
${ex.length ? `<section><h2>Entrance exams for this career</h2>${linkList(ex.map((e) => [`/exams/${e.id}/`, e.name, [e.stream, real(e.body) ? e.body : ''].filter(Boolean).join(' · ')]))}</section>` : ''}
${(c.pros && c.pros.length) || (c.cons && c.cons.length) ? `<section class="two"><div class="pros"><h2>Good things</h2>${list(c.pros)}</div><div class="cons"><h2>Hard things</h2>${list(c.cons)}</div></section>` : ''}
${similar.length ? `<section><h2>Similar careers in ${esc(c.category)}</h2>${linkList(similar.map((x) => [`/careers/${x.id}/`, x.title, x.salary ? x.salary + ' (approx.)' : '']))}</section>` : ''}
<section class="box"><h2>Not sure this is the one?</h2><p>The free Plan4it.co quiz matches your interests, marks and budget to careers like this one, and shows the colleges and exams for each.</p><div class="cta"><a class="btn primary" href="/#confusedMode">Take the free career quiz</a><a class="btn" href="/careers/">See all careers</a></div></section>`;
  const description = clip(`${c.title}: what the job is, typical pay in India (${c.salary}, approx.), skills, entrance exams and a step-by-step roadmap. ${c.overview}`, 158);
  const occ = { '@context': 'https://schema.org', '@type': 'Occupation', name: c.title, description: c.overview, occupationLocation: { '@type': 'Country', name: 'India' },
    skills: (c.skills || []).join(', ') || undefined, url: SITE + urlPath };
  if (c.salaryMin && c.salaryMax) occ.estimatedSalary = { '@type': 'MonetaryAmountDistribution', name: 'approximate', currency: 'INR', duration: 'P1Y', minValue: Math.round(c.salaryMin * 1e5), maxValue: Math.round(c.salaryMax * 1e5) };
  out(urlPath, page({ urlPath, title: `${c.title}: career, salary, skills and roadmap in India | Plan4it.co`, description, body, ld: [cr.ld, occ], section: 'careers' }));
  sitemap.push({ loc: SITE + urlPath, pri: '0.7' });
  written.push(urlPath);
}
careers.forEach(careerPage);

{
  const cats = [...new Set(careers.map((c) => c.category))];
  const urlPath = '/careers/';
  const cr = crumbs([['/', 'Home'], [urlPath, 'Careers']]);
  const body = `${cr.html}
<p class="eyebrow">Career guide for India</p>
<h1>All careers, A to Z by field</h1>
<p class="lede">${careers.length} careers, each with typical pay, the skills you need, the entrance exams and a step-by-step roadmap from Class 12. Pick a field, or take the free quiz to see which careers fit you.</p>
<div class="cta"><a class="btn primary" href="/#confusedMode">Take the free career quiz</a><a class="btn" href="/#explorer">Compare careers in the app</a></div>
<ul class="index-nav" aria-label="Fields">${cats.map((k) => `<li><a href="#${slug(k)}">${esc(k)}</a></li>`).join('')}</ul>
${cats.map((k) => { const cs = careers.filter((c) => c.category === k).sort((a, b) => a.title.localeCompare(b.title)); return `<section class="group" id="${slug(k)}"><h2>${esc(k)}<small>${cs.length} careers</small></h2>${linkList(cs.map((c) => [`/careers/${c.id}/`, c.title, c.salary ? c.salary + ' (approx.)' : '']))}</section>`; }).join('\n')}`;
  const ld = { '@context': 'https://schema.org', '@type': 'CollectionPage', name: 'All careers in India', url: SITE + urlPath, about: 'Careers in India for Class 10–12 students' };
  out(urlPath, page({ urlPath, title: `Career options in India after Class 12: ${careers.length} careers with pay and roadmaps | Plan4it.co`, description: clip(`Explore ${careers.length} career options in India by field, with typical pay, skills, entrance exams and step-by-step roadmaps from Class 12. Free career quiz included.`, 158), body, ld: [cr.ld, ld], section: 'careers' }));
  sitemap.push({ loc: SITE + urlPath, pri: '0.9' });
}

/* ---------- exams ---------- */
const upcoming = (e) => !e.datesUnknown && e.examDate && e.examDate >= TODAY;
function examScore(e) {
  // How many real facts the page has. Pages below the bar are kept for visitors but marked noindex.
  return ['eligibility', 'courses', 'mode', 'duration', 'attempts', 'examFee', 'pattern', 'ageLimit'].filter((k) => real(e[k])).length
    + (upcoming(e) || e.lastCycle ? 1 : 0) + (e.verifiedLinks && e.verifiedLinks.length ? 1 : 0) + (real(e.site) ? 1 : 0);
}
let examIndexed = 0, examNoindex = 0;
function examPage(e) {
  const urlPath = `/exams/${e.id}/`;
  const cr = crumbs([['/', 'Home'], ['/exams/', 'Exams'], [urlPath, e.name]]);
  const site = real(e.site) ? httpUrl(e.site) : '';
  const usedBy = careersByExam.get(e.id) || [];
  const similar = exams.filter((x) => x !== e && x.stream === e.stream).slice(0, 8);
  const noindex = examScore(e) < 5;
  noindex ? examNoindex++ : examIndexed++;
  const lede = [real(e.body) ? `${e.name} is conducted by ${e.body}.` : '', real(e.courses) ? `It is used for admission to ${e.courses.replace(/\.$/, '')}.` : ''].filter(Boolean).join(' ');

  let dates = '';
  if (upcoming(e)) {
    const rows = [];
    if (e.info && e.info.length) {
      for (const i of e.info) {
        rows.push(['Exam dates', i.dates], ['Registration', i.registration], ['Admit card', i.admit], ['Result', i.result], ['Status', i.status]);
      }
    } else {
      rows.push(['Exam', e.dateShort || fmtDate(e.examDate)], ['Registration', e.regText], ['Status', e.dateStatus]);
    }
    const r = rows.filter(([, v]) => real(v));
    if (r.length) dates = `<section><h2>Upcoming dates</h2><div class="table-wrap"><table><tbody>${r.map(([k, v]) => `<tr><th scope="row">${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')}</tbody></table></div><p class="note">${e.dateStatus && /tentative|expected/i.test(e.dateStatus) ? 'These dates are expected, not yet announced. ' : ''}Dates move. Confirm on the official website before you plan around them. The app shows the latest dates and can remind you before registration closes.</p></section>`;
  } else if (e.lastCycle) {
    const lc = e.lastCycle;
    const r = [['Registration', lc.reg], ['Exam', lc.exam], ['Result', lc.result]].filter(([, v]) => real(v));
    if (r.length) dates = `<section><h2>Last cycle (${esc(lc.year)})</h2><div class="table-wrap"><table><tbody>${r.map(([k, v]) => `<tr><th scope="row">${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')}</tbody></table></div><p class="note">The next dates are not out yet. Last year's timing is a rough guide only.</p></section>`;
  }
  const links = (e.verifiedLinks || []).filter((l) => /^https?:\/\//.test(l[1]));
  const body = `${cr.html}
<p class="eyebrow">${esc(e.stream || 'Entrance exam')} · Entrance exam</p>
<h1>${esc(e.name)}</h1>
${lede ? `<p class="lede">${esc(lede)}</p>` : ''}
<div class="cta"><a class="btn primary" href="/#exam/${esc(e.id)}">Open in Plan4it.co</a>${site ? `<a class="btn" href="${esc(site)}" rel="noopener">Official site: ${esc(hostOf(site))}</a>` : ''}</div>
<dl class="facts">
${fact('Conducted by', e.body)}${fact('Eligibility', e.eligibility)}${fact('Courses', e.courses)}${fact('Mode', e.mode)}${fact('Duration', e.duration)}${fact('Attempts', e.attempts)}${fact('Age limit', e.ageLimit)}${fact('Difficulty', e.difficulty)}
</dl>
${real(e.examFee) ? `<section><h2>Application fee</h2><p>${esc(e.examFee)}</p>${e.verifiedCycle ? `<p class="note">From the official ${esc(e.verifiedCycle)} notice.</p>` : ''}</section>` : ''}
${real(e.pattern) ? `<section><h2>Exam pattern</h2><p>${esc(e.pattern)}</p></section>` : ''}
${dates}
${real(e.competitionNote) && !GENERIC_COMPETITION.test(e.competitionNote) ? `<section><h2>How competitive it is</h2><p>${esc(e.competitionNote)}</p></section>` : ''}
${real(e.prepTip) ? `<section><h2>Preparation tip</h2><p>${esc(e.prepTip)}</p></section>` : ''}
${links.length ? `<section><h2>Official sources</h2><ul class="plain">${links.map((l) => `<li><a href="${esc(l[1])}" rel="noopener">${esc(l[0])}</a></li>`).join('')}</ul>${e.verifiedOn ? `<p class="note">Checked by Plan4it.co on ${esc(fmtDate(e.verifiedOn))}.</p>` : ''}</section>` : ''}
${usedBy.length ? `<section><h2>Careers this exam leads to</h2>${linkList(usedBy.slice(0, 12).map((c) => [`/careers/${c.id}/`, c.title, c.salary ? c.salary + ' (approx.)' : '']))}</section>` : ''}
${similar.length ? `<section><h2>Other ${esc(e.stream)} exams</h2>${linkList(similar.map((x) => [`/exams/${x.id}/`, x.name, real(x.body) ? x.body : '']))}</section>` : ''}
<section class="box warn"><p>Fees, dates and eligibility change every year. Always check the official notice${site ? ` on ${esc(hostOf(site))}` : ''} before you apply or pay.</p></section>`;
  const description = clip(`${e.name}${real(e.body) ? ` (${e.body})` : ''}: eligibility, ${real(e.examFee) ? 'fee, ' : ''}${real(e.pattern) ? 'pattern, ' : ''}dates and the official website. ${real(e.courses) ? 'For admission to ' + e.courses + '.' : ''}`, 158);
  const ld = { '@context': 'https://schema.org', '@type': 'WebPage', name: e.name, url: SITE + urlPath, about: { '@type': 'Thing', name: e.name + ' entrance exam' }, description };
  out(urlPath, page({ urlPath, title: `${e.name}: eligibility, fee, pattern and dates | Plan4it.co`, description, body, ld: [cr.ld, ld], section: 'exams', noindex }));
  if (!noindex) sitemap.push({ loc: SITE + urlPath, pri: '0.6' });
  written.push(urlPath);
}
exams.forEach(examPage);

{
  const streams = [...new Set(exams.map((e) => e.stream || 'Other'))];
  const urlPath = '/exams/';
  const cr = crumbs([['/', 'Home'], [urlPath, 'Exams']]);
  const body = `${cr.html}
<p class="eyebrow">Entrance exams in India</p>
<h1>Entrance exams by stream</h1>
<p class="lede">${exams.length} entrance and recruitment exams, with who runs them, eligibility, fees and dates where they are known, and a link to each official website.</p>
<div class="cta"><a class="btn primary" href="/#exams">Track exam dates in the app</a><a class="btn" href="/#confusedMode">Take the free career quiz</a></div>
<ul class="index-nav" aria-label="Streams">${streams.map((k) => `<li><a href="#${slug(k)}">${esc(k)}</a></li>`).join('')}</ul>
${streams.map((k) => { const xs = exams.filter((e) => (e.stream || 'Other') === k).sort((a, b) => a.name.localeCompare(b.name)); return `<section class="group" id="${slug(k)}"><h2>${esc(k)}<small>${xs.length} exams</small></h2>${linkList(xs.map((e) => [`/exams/${e.id}/`, e.name, real(e.body) ? e.body : '']))}</section>`; }).join('\n')}`;
  out(urlPath, page({ urlPath, title: `Entrance exams in India after Class 10 and 12: eligibility, fees and dates | Plan4it.co`, description: clip(`${exams.length} entrance exams in India by stream: engineering, medical, law, design, defence, banking and more, with eligibility, fees, dates and official websites.`, 158), body, ld: [cr.ld], section: 'exams' }));
  sitemap.push({ loc: SITE + urlPath, pri: '0.9' });
}

/* ---------- degrees ---------- */
function degreePage(d) {
  const urlPath = `/degrees/${d.slug}/`;
  const cr = crumbs([['/', 'Home'], ['/degrees/', 'Degrees'], [urlPath, d.key]]);
  const cs = careersForDegree(d.key);
  const others = DEGREES.filter((x) => x !== d);
  const body = `${cr.html}
<p class="eyebrow">Degree guide · ${esc(d.duration)}</p>
<h1>${esc(d.name)}</h1>
<p class="lede">${esc(d.focus)}</p>
<div class="cta"><a class="btn primary" href="/#colleges">Find colleges in the app</a><a class="btn" href="/#confusedMode">Take the free career quiz</a></div>
<dl class="facts">${fact('Degree', d.key)}${fact('Duration', d.duration)}</dl>
${real(d.subjects) ? `<section><h2>What you study</h2><p>${esc(d.subjects)}</p></section>` : ''}
${real(d.spec) ? `<section><h2>Popular specialisations</h2><ul class="chips">${d.spec.replace(/\.$/, '').split(/,\s*/).map((s) => `<li>${esc(s)}</li>`).join('')}</ul></section>` : ''}
${cs.length ? `<section><h2>Careers that start with a ${esc(d.key)}</h2><p>These careers list a ${esc(d.key)} as one of the routes in.</p>${linkList(cs.map((c) => [`/careers/${c.id}/`, c.title, c.salary ? c.salary + ' (approx.)' : '']))}</section>` : ''}
<section><h2>Other degree guides</h2>${linkList(others.map((x) => [`/degrees/${x.slug}/`, x.key, x.duration]))}</section>`;
  const description = clip(`${d.name}: duration (${d.duration}), what you study, specialisations and the careers it leads to in India. ${d.focus}`, 158);
  out(urlPath, page({ urlPath, title: `${d.key} course: subjects, specialisations and careers | Plan4it.co`, description, body, ld: [cr.ld, { '@context': 'https://schema.org', '@type': 'WebPage', name: d.name, url: SITE + urlPath, description }], section: 'degrees' }));
  sitemap.push({ loc: SITE + urlPath, pri: '0.6' });
  written.push(urlPath);
}
DEGREES.forEach(degreePage);
{
  const urlPath = '/degrees/';
  const cr = crumbs([['/', 'Home'], [urlPath, 'Degrees']]);
  const body = `${cr.html}
<p class="eyebrow">Degree guides</p>
<h1>Which degree after Class 12?</h1>
<p class="lede">What each common undergraduate degree covers, how long it takes, the usual specialisations and the careers it leads to.</p>
<div class="cta"><a class="btn primary" href="/#confusedMode">Take the free career quiz</a><a class="btn" href="/#colleges">Find colleges in the app</a></div>
<section>${linkList(DEGREES.map((d) => [`/degrees/${d.slug}/`, d.name, d.duration]))}</section>`;
  out(urlPath, page({ urlPath, title: 'Degrees after Class 12: B.Tech, B.Sc, B.Com, BBA, BA, BCA, B.Des | Plan4it.co', description: 'Compare common degrees after Class 12 in India: duration, subjects, specialisations and the careers each one leads to.', body, ld: [cr.ld], section: 'degrees' }));
  sitemap.push({ loc: SITE + urlPath, pri: '0.8' });
}

/* ---------- remove pages whose record no longer exists ---------- */
for (const dir of ['careers', 'exams', 'degrees']) {
  const base = path.join(ROOT, dir);
  for (const name of fs.readdirSync(base)) {
    const p = path.join(base, name);
    if (fs.statSync(p).isDirectory() && !written.includes(`/${dir}/${name}/`)) fs.rmSync(p, { recursive: true });
  }
}

/* ---------- sitemap ---------- */
fs.writeFileSync(path.join(ROOT, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by scripts/build-seo-pages.mjs. Do not edit by hand. -->
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${sitemap.map((u) => `  <url><loc>${u.loc}</loc><lastmod>${TODAY}</lastmod><priority>${u.pri}</priority></url>`).join('\n')}
</urlset>
`);

console.log(`careers: ${careers.length} pages, exams: ${exams.length} pages (${examIndexed} indexed, ${examNoindex} noindex), degrees: ${DEGREES.length} pages, sitemap: ${sitemap.length} URLs`);
