#!/usr/bin/env python3
"""Logic tests for the two business-critical scoring/ranking functions that
drive real recommendations: scoreCareerForWizard() (the career-quiz scorer)
and generateBackupPlan()/renderBackupPlan() (the backup-college ranker).

Unlike smoke_test.py (does the page load at all), these call the *actual*
production functions inside a real browser via Playwright and check their
outputs against the behavior the app promises a student -- a matching
interest should score higher, a named career should score higher, backups
should be sorted and labeled the way the UI claims. A change that breaks
one of these invariants (wrong sort direction, flipped threshold, wrong
field) is exactly the kind of mistake 13K lines of inline JS with no types
can hide silently until a real student sees a nonsensical recommendation.

Requires: pip install playwright && playwright install --with-deps chromium
"""
import http.server
import socket
import sys
import threading
import contextlib
from playwright.sync_api import sync_playwright


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def local_server():
    port = free_port()
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, **kw)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


QUIZ_TEST_JS = """
() => {
    const problems = [];
    const careers = careersData;

    // Pick a career whose category the quiz can target, and one in a
    // clearly different, non-overlapping category, as the control.
    const byCategory = {};
    careers.forEach(c => { (byCategory[c.category] = byCategory[c.category] || []).push(c); });
    const categories = Object.keys(byCategory).filter(cat => byCategory[cat].length > 0);
    if (categories.length < 2) { problems.push('Not enough distinct categories in careersData to run the test.'); return { problems }; }

    const matchCategory = categories[0];
    const offCategory = categories.find(cat => cat !== matchCategory && !byCategory[cat].some(c => c.interestTags && c.interestTags.includes(matchCategory)));
    if (!offCategory) { problems.push('Could not find a non-overlapping control category.'); return { problems }; }

    const quizInterest = typeof QZ_CAT_TO_INT === 'object'
        ? Object.keys(QZ_CAT_TO_INT).find(k => QZ_CAT_TO_INT[k] === matchCategory) || matchCategory
        : matchCategory;

    const careerA = byCategory[matchCategory][0];   // should match the student's stated interest
    const careerB = byCategory[offCategory].find(c => !(c.interestTags || []).includes(quizInterest)) || byCategory[offCategory][0];

    const baseAnswers = { interest: quizInterest, interests3: [quizInterest], workStyle: 'Logic', constraint: 'Fast', mentioned: [], values: [] };

    const scoreA = scoreCareerForWizard(careerA, baseAnswers).score;
    const scoreB = scoreCareerForWizard(careerB, baseAnswers).score;

    // 1. A career matching the student's #1 stated interest must outrank an
    //    unrelated career, holding every other answer equal.
    if (!(scoreA > scoreB)) {
        problems.push(`Expected interest-matched career (${careerA.title}: ${scoreA}) to outscore unrelated career (${careerB.title}: ${scoreB}), but it did not.`);
    }

    // 2. A career the student explicitly named ("mentioned") must score
    //    higher than the identical career without that flag -- the +70
    //    "you said this interests you" bonus must actually apply.
    const unmentioned = scoreCareerForWizard(careerB, baseAnswers).score;
    const mentionedAnswers = Object.assign({}, baseAnswers, { mentioned: [careerB.id] });
    const mentioned = scoreCareerForWizard(careerB, mentionedAnswers).score;
    if (!(mentioned > unmentioned)) {
        problems.push(`Expected naming a career to raise its score (unmentioned=${unmentioned}, mentioned=${mentioned}), but it did not.`);
    }

    // 3. Score must always be a finite number, never NaN/undefined, across
    //    a representative sample of careers with partial/missing optional
    //    answer fields -- a NaN here means a student sees careers sorted
    //    in a broken, meaningless order with no visible error.
    const sampleAnswerSets = [
        { interest: 'Undecided', workStyle: '', constraint: '' },
        { interests3: [], workStyle: 'Creative', constraint: 'Deep', values: ['earn', 'stable'] },
        { interest: quizInterest, workStyle: 'People', constraint: 'Budget', values: ['help', 'own', 'skilled'], budget: 'u1', level: 'low' },
        {},
    ];
    const sampleCareers = careers.filter((_, i) => i % 37 === 0).slice(0, 15);
    let nanCount = 0;
    sampleCareers.forEach(c => {
        sampleAnswerSets.forEach(ans => {
            const r = scoreCareerForWizard(c, ans);
            if (typeof r.score !== 'number' || !isFinite(r.score)) nanCount++;
        });
    });
    if (nanCount > 0) {
        problems.push(`${nanCount} of ${sampleCareers.length * sampleAnswerSets.length} (career, partial-answers) combinations produced a non-finite score.`);
    }

    return { problems, scoreA, scoreB, careerA: careerA.title, careerB: careerB.title };
}
"""

BACKUP_TEST_JS = """
(priority) => {
    const problems = [];
    const examId = 'jee-main-advanced';
    const list = BACKUP_COLLEGES[examId];
    if (!list || list.length < 5) { problems.push('BACKUP_COLLEGES.jee-main-advanced has fewer than 5 entries; cannot test top-5 ranking.'); return { problems }; }

    // A synthetic target college that matches none of the real entries by
    // name, so every real entry is a legitimate "other" candidate. Plain
    // assignment (no "window."/"let"/"const") on purpose: BACKUP_TARGET is
    // declared with top-level `let` in index.html, which lives in the
    // global lexical environment, NOT as a `window` property -- setting
    // `window.BACKUP_TARGET` silently creates an unrelated property and
    // leaves the real binding (and this test) untouched.
    BACKUP_TARGET = { name: 'IIT Delhi (test target)', cutoff: 99.7, location: 'New Delhi, Delhi', knownId: null };
    document.getElementById('backup-exam').value = examId;
    document.getElementById('backup-score').value = '88';
    document.getElementById('backup-city').value = priority === 'location' ? 'Hyderabad' : '';
    document.querySelectorAll('input[name=\"backup-priority\"]').forEach(r => { r.checked = (r.value === priority); });

    generateBackupPlan();

    const cards = Array.from(document.querySelectorAll('#backup-cards > div'));
    if (cards.length === 0 || cards.length > 5) problems.push(`Expected 1-5 backup cards, got ${cards.length}.`);

    const score = 88;
    const preferredCity = priority === 'location' ? 'hyderabad' : 'new delhi';
    const rendered = cards.map(card => {
        const name = card.querySelector('h4').textContent.trim();
        const oddsLabel = card.querySelector('span.text-xs.font-semibold').textContent.trim();
        return { name, oddsLabel };
    });

    // Target must never appear among its own backups.
    if (rendered.some(r => r.name === BACKUP_TARGET.name)) {
        problems.push('The target college itself appeared in its own backup list.');
    }

    // Recompute the documented ranking formula independently from the same
    // source data and check the UI's rendered order matches it exactly --
    // this is what actually catches a flipped sort, wrong field, or wrong
    // threshold introduced by a future edit.
    const expected = list.map(c => {
        let rank;
        if (priority === 'placement') rank = c.placementRate * 10;
        else if (priority === 'salary') rank = c.avgSalary * 100;
        else if (priority === 'location') { const m = c.location.toLowerCase().includes(preferredCity); rank = (m ? 1000 : 0) + c.placementRate * 5; }
        else { const closeness = 100 - Math.abs(score - c.cutoff); rank = (c.placementRate * 5) + (c.avgSalary * 50) + (closeness * 2); }
        return { c, rank };
    }).sort((a, b) => b.rank - a.rank).slice(0, 5);

    const expectedNames = expected.map(e => e.c.name);
    const renderedNames = rendered.map(r => r.name);
    if (JSON.stringify(expectedNames) !== JSON.stringify(renderedNames)) {
        problems.push(`[${priority}] Rendered order ${JSON.stringify(renderedNames)} does not match the documented ranking formula's order ${JSON.stringify(expectedNames)}.`);
    }

    // Odds label must match the gap thresholds the summary panel itself
    // promises (>=5 Very Likely, >=-5 Likely, else Possible).
    expected.forEach((e, i) => {
        const gap = +(score - e.c.cutoff).toFixed(1);
        const want = gap >= 5 ? 'Very Likely' : gap >= -5 ? 'Likely' : 'Possible';
        const got = rendered[i] && rendered[i].oddsLabel;
        if (got !== want) problems.push(`[${priority}] ${e.c.name}: expected odds label "${want}" (gap ${gap}) but got "${got}".`);
    });

    return { problems, renderedNames, expectedNames };
}
"""


def main():
    problems = []

    with local_server() as base_url:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"{base_url}/index.html", wait_until="networkidle")
            page.wait_for_timeout(1000)

            quiz_result = page.evaluate(QUIZ_TEST_JS)
            problems.extend(f"[scoreCareerForWizard] {p_}" for p_ in quiz_result.get("problems", []))

            for priority in ("placement", "salary", "location", "balanced"):
                backup_result = page.evaluate(BACKUP_TEST_JS, priority)
                problems.extend(f"[generateBackupPlan] {p_}" for p_ in backup_result.get("problems", []))

            browser.close()

    if problems:
        print("Logic tests FAILED:\n")
        for p_ in problems:
            print(f"  - {p_}")
        sys.exit(1)

    print("Logic tests OK: quiz scoring and backup-plan ranking match the behavior they promise students.")


if __name__ == "__main__":
    main()
