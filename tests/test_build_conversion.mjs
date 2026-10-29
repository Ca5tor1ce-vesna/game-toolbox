import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../modules/honkai-star-rail/features/aha-speed/ui.js', import.meta.url), 'utf8');
const { default: feature } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
assert.equal(typeof feature.convertSavedBuild, 'function', '配装转换应提供可单独验证的入口');
const catalog = {
  lightcones: [{ id: 'cone', name: '当她决定看见' }],
  relicSets: [{ id: 'set', name: '神的瞬息欢愉' }],
};
const spec = { name: '爻光', elation: true, baseSpd: 101, traceSpd: 9, lcBaseSpd: 0, rotation: 'skill' };
const resolved = {
  entry: { name: '测试配装', savedAt: 'now', config: { lightconeId: 'cone', superimpose: 1, eidolon: 2, relic: { fourPieceId: 'set' }, advance: { custom: 12 }, aha: { err: 19.4 } } },
  result: { speed: { pct: 30, final: 165.3, base: 101 }, effects: { enabled: ['field'], speed: [{ id: 'field', origin: '角色·星魂', rank: 2, apply: 'team', kind: 'pct', value: 10 }] } },
};
const unit = feature.convertSavedBuild('1502', resolved, 3, spec, catalog);
assert.equal(unit.equipment.godJoy, true);
assert.equal(unit.equipment.hasYaoLc, true);
assert.equal(unit.permPct, 14);
assert.equal(unit.initAdv, 12);
assert.equal(unit.err, 19.4);
assert.ok(Math.abs(unit.sourceBuild.baselineSpeed - 155.2) < 1e-9);
assert.ok(Math.abs((unit.baseSpd * (1 + (unit.permPct + 6) / 100) + unit.traceSpd + unit.permFlat) - 155.2) < 1e-9);
assert.notEqual(unit.sourceBuild.config, resolved.entry.config);
assert.match(unit.sourceBuild.note, /二魂结界/);
console.log('[OK] 配装转换保持速度、条件效果和存档独立');
