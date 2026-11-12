import assert from 'node:assert/strict';
import { rugGreeting, nextLocalDayDelay } from '../discprobe/web/home/lobby-weekday.js';

const zh = ['周日愉快', '周一愉快', '周二愉快', '周三愉快', '周四愉快', '周五愉快', '周六愉快'];
const en = ['HAPPY SUNDAY', 'HAPPY MONDAY', 'HAPPY TUESDAY', 'HAPPY WEDNESDAY', 'HAPPY THURSDAY', 'HAPPY FRIDAY', 'HAPPY SATURDAY'];
// Local dates around a UTC date boundary: the visible weekday must stay local.
for (let day = 0; day < 7; day++) {
  const date = new Date(2026, 10, 8 + day, 23, 59, 59, 900);
  assert.equal(rugGreeting('zh', date), zh[day]);
  assert.equal(rugGreeting('en', date), en[day]);
  assert.equal(nextLocalDayDelay(date), 150);
  assert.equal(rugGreeting('en', new Date(+date + 100)), en[(day + 1) % 7]);
}
// Local daylight-saving days are not always 24 hours.
process.env.TZ = 'America/Toronto';
assert.equal(nextLocalDayDelay(new Date(2026, 2, 8)), 23 * 3600000 + 50);
assert.equal(nextLocalDayDelay(new Date(2026, 10, 1)), 25 * 3600000 + 50);
console.log('Lobby weekday: both languages, local midnight and DST passed');
