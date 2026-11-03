#!/usr/bin/env node
// Precompiles the Tailwind utilities this app actually uses into a static CSS file
// (assets/tailwind.css), replacing the cdn.tailwindcss.com runtime JIT compiler.
//
// Run this any time Tailwind classes are added/removed/changed in index.html:
//   node scripts/build-tailwind.mjs
//
// How it works: scans index.html as plain text for anything that *looks* like a
// utility class (Tailwind's own extractor does the same thing — it doesn't parse
// HTML/JS, it just tokenizes). Over-matching is harmless (bogus tokens are
// silently dropped by the compiler); under-matching would silently drop real
// styles, so the tokenizer here is deliberately broad.

import { compile } from 'tailwindcss';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..');
const htmlPath = path.join(repoRoot, 'index.html');
const outPath = path.join(repoRoot, 'assets', 'tailwind.css');

const html = readFileSync(htmlPath, 'utf8');

// Broad tokenizer: split on characters that can never appear inside a Tailwind
// candidate (quotes, angle brackets, '=', whitespace, ';', braces) and keep
// everything else as one token — this preserves arbitrary-value classes like
// `text-[11px]` or `shadow-[0_0_0_3px_rgba(0,0,0,.1)]` intact.
const tokens = new Set(html.split(/["'`<>=\s;{}]+/).filter(Boolean));
const candidates = [...tokens];

// Brand palette: Tailwind's own "sky" scale, chosen for the dark-only theme
// (graphite surfaces + a cyan-leaning blue accent — see docs/PRE_LAUNCH_CHECKLIST.md
// "Theme" entry). Keep this in sync with the html.dark overrides in index.html's
// <style> block if the accent hue ever changes again.
const css = `
@import "tailwindcss";

@theme {
  --color-brand-50: #f0f9ff;
  --color-brand-100: #e0f2fe;
  --color-brand-200: #bae6fd;
  --color-brand-300: #7dd3fc;
  --color-brand-400: #38bdf8;
  --color-brand-500: #0ea5e9;
  --color-brand-600: #0284c7;
  --color-brand-700: #0369a1;
  --color-brand-800: #075985;
  --color-brand-900: #0c4a6e;
  --color-brand-950: #082f49;
}
`;

// Resolve `@import "tailwindcss"` (and any package it in turn imports) against
// real node_modules package.json "exports"/"style" fields, same as a bundler would.
async function loadStylesheet(id, base) {
    if (id === 'tailwindcss') {
        const pkgPath = require.resolve('tailwindcss/package.json', { paths: [base] });
        const pkgDir = path.dirname(pkgPath);
        const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
        const entry = pkg.style || pkg.exports?.['.']?.style || 'index.css';
        const fullPath = path.join(pkgDir, entry);
        return { path: fullPath, base: path.dirname(fullPath), content: readFileSync(fullPath, 'utf8') };
    }
    throw new Error(`Don't know how to resolve stylesheet import "${id}" (base: ${base})`);
}

const { build } = await compile(css, { base: repoRoot, loadStylesheet });
let output = build(candidates);

// Minify: Tailwind's compile() output here isn't minified by default without
// lightningcss wired in as a postcss step; do a safe, conservative minification
// (strip comments and collapse whitespace) rather than pull in a bundler.
output = output
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/\s+/g, ' ')
  .replace(/\s*([{}:;,])\s*/g, '$1')
  .replace(/;}/g, '}')
  .trim();

writeFileSync(outPath, output);
console.log(`Wrote ${outPath} (${(output.length / 1024).toFixed(1)} KB, ${candidates.length} candidate tokens scanned)`);
