// Local calendar day; no service or network state is needed for the rug.
const ZH = ["日", "一", "二", "三", "四", "五", "六"];
const EN = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"];
export function rugGreeting(lang, date = new Date()) {
  return lang === "en" ? `HAPPY ${EN[date.getDay()]}` : `周${ZH[date.getDay()]}愉快`;
}
export function nextLocalDayDelay(date = new Date()) {
  const next = new Date(date);
  next.setHours(24, 0, 0, 0);
  return next - date + 50;
}
