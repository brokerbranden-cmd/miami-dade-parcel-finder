// Minimal D1 stand-in over node:sqlite (Node >= 22) for tests: prepare().bind().all()/run()/first(), batch() in one transaction.
import { DatabaseSync } from 'node:sqlite';
export function makeD1() {
  const db = new DatabaseSync(':memory:');
  const stmt = (sql, args = []) => ({
    bind: (...a) => stmt(sql, a),
    _exec() { const s = db.prepare(sql); if (/^\s*(SELECT|WITH)/i.test(sql)) return { results: s.all(...args), meta: {} }; const r = s.run(...args); return { results: [], meta: { changes: Number(r.changes) } }; },
    async all() { return this._exec(); }, async run() { return this._exec(); }, async first() { return (this._exec().results || [])[0] || null; }
  });
  return { _db: db, prepare: sql => stmt(sql), async batch(list) { db.exec('BEGIN'); try { const out = list.map(s => s._exec()); db.exec('COMMIT'); return out; } catch (e) { db.exec('ROLLBACK'); throw e; } } };
}
