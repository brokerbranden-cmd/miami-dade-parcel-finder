/* Teardown rule (pure logic, no DOM) - same rule as the Parcel Seeker's teardown.py port:
   basic  = single-family / 2-9 unit use (DOR 01xx / 08xx), land >= min share of total value, built in or before max year.
   strong = basic AND (lot is not under the zone minimum, when that toggle is on) AND zoning allows
            min_unit_multiple x the existing units (density), else min_sqft_multiple x the building (FAR or
            lot coverage x stories), else min_story_multiple x the stories.
   Companies / organizations that bought within the last `exclude_corp_years` years (default 3, 0 = off) are left out: a recent corporate buyer is usually mid-project.
   Zone record z = {upa, stories, min_lot_sf, lot_cov, far, sf (1 single-family zone), pd (planned dev)}; null = unknown. */
(function (root) {
  'use strict';
  const SQFT_AC = 43560;
  const DEFAULT_RULES = Object.freeze({ min_land_share: 0.80, max_year_built: 1969, min_unit_multiple: 3, min_sqft_multiple: 3, min_story_multiple: 3, lot_split_factor: 2, enforce_min_lot: true, exclude_corp_years: 3 });
  const pos = x => x != null && x > 0;
  const r1 = x => Math.round(x * 10) / 10;
  const isTarget = code => code != null && ((code >= 100 && code < 200) || (code >= 800 && code < 900));
  // p = {code, land, total, yb, lot, units, stories, bldg, corpHeld (years since a company / organization owner bought; null / undefined when not a company or unknown)}
  function upside(p, z) {
    z = z || {};
    const eu = Math.max(p.units || 0, 1), es = Math.max(p.stories || 0, 1);
    let allowed = null, um = null, sm = null, sqft = null, basis = null, qm = null, below = null, split = null;
    if (pos(z.upa) && p.lot > 0) { allowed = Math.floor(p.lot / SQFT_AC * z.upa + 1e-9); um = r1(allowed / eu); }
    if (pos(z.stories)) sm = r1(z.stories / es);
    if (p.lot > 0) {
      if (pos(z.far)) { sqft = Math.floor(p.lot * z.far); basis = 'FAR'; }
      else if (pos(z.lot_cov) && pos(z.stories)) { sqft = Math.floor(p.lot * Math.min(z.lot_cov, 100) / 100 * z.stories); basis = 'coverage x stories'; }
    }
    if (sqft != null && p.bldg > 0) qm = r1(sqft / p.bldg);
    if (!z.pd && pos(z.min_lot_sf) && p.lot > 0) { below = p.lot < z.min_lot_sf; if (z.sf != null) split = !!z.sf; }
    return { allowed, um, sm, sqft, basis, qm, below, sfzone: split };
  }
  function evaluate(p, z, rules) {
    rules = rules || DEFAULT_RULES; z = z || {};
    const reasons = [];
    if (!isTarget(p.code)) reasons.push('use is not single-family or 2-9 units');
    if (!(p.total > 0)) reasons.push('no total value');
    else if (p.land > p.total) reasons.push('land value exceeds total value');
    else if (p.land / p.total < rules.min_land_share) reasons.push(`land is ${Math.round(p.land / p.total * 100)}% of value, under ${Math.round(rules.min_land_share * 100)}%`);
    if (!(p.yb > 0 && p.yb <= rules.max_year_built)) reasons.push(`year built ${p.yb || 'unknown'} is after ${rules.max_year_built}`);
    if (rules.exclude_corp_years > 0 && p.corpHeld != null && p.corpHeld < rules.exclude_corp_years) reasons.push(`owned by a company that bought ${r1(p.corpHeld)} years ago (rule skips companies that bought in the last ${rules.exclude_corp_years} years)`);
    const up = upside(p, z), basic = reasons.length === 0;
    let strong = false;
    if (basic) {
      if (rules.enforce_min_lot && up.below) reasons.push(`lot is ${Math.round(p.lot).toLocaleString('en-US')} sf, under the zone's ${Math.round(z.min_lot_sf).toLocaleString('en-US')} sf minimum`);
      else if (up.um != null) { strong = up.um >= rules.min_unit_multiple; if (!strong) reasons.push(`zoning allows ${up.allowed} unit(s), only ${up.um}x what's there`); }
      else if (up.qm != null) { strong = up.qm >= rules.min_sqft_multiple; if (!strong) reasons.push(`zoning allows ${up.sqft.toLocaleString('en-US')} sf, only ${up.qm}x the building`); }
      else if (up.sm != null) { strong = up.sm >= rules.min_story_multiple; if (!strong) reasons.push(`zoning allows only ${up.sm}x the stories`); }
      else reasons.push("no zoning numbers, can't confirm upside");
    }
    const split = up.sfzone === true && p.lot >= rules.lot_split_factor * z.min_lot_sf;
    return Object.assign({ basic, strong, tier: strong ? 2 : basic ? 1 : 0, reasons, split }, up);
  }
  // fast path: um/qm/sm NaN = unknown, below 0/1. Must agree with evaluate().
  // corpHeld: years since a company owner bought (Infinity / undefined = not a company or unknown)
  function tierFast(code, land, total, yb, um, qm, sm, below, r, corpHeld) {
    if (!isTarget(code)) return 0;
    if (r.exclude_corp_years > 0 && corpHeld < r.exclude_corp_years) return 0;
    if (!(total > 0) || land > total || land / total < r.min_land_share) return 0;
    if (!(yb > 0 && yb <= r.max_year_built)) return 0;
    if (r.enforce_min_lot && below) return 1;
    if (um === um) return um >= r.min_unit_multiple ? 2 : 1;
    if (qm === qm) return qm >= r.min_sqft_multiple ? 2 : 1;
    if (sm === sm) return sm >= r.min_story_multiple ? 2 : 1;
    return 1;
  }
  root.PFTeardown = { DEFAULT_RULES, upside, evaluate, tierFast, isTarget, SQFT_AC };
})(typeof window !== 'undefined' ? window : globalThis);
