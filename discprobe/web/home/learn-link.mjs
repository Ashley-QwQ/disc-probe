export const learnLabel = english => english ? "How a disc becomes a picture" : "光盘怎么变成图";

export function learnURL(english) {
  const file = english ? "how-disc-images-work.html" : "how-disc-images-work.zh.html";
  return new URL("./learn/" + file, import.meta.url).href;
}

export const calibrationLabel = english => english ? "Why calibrate before burning a picture?" : "刻图前为什么要标定？";

export function calibrationURL(english) {
  const file = english ? "why-calibrate.html" : "why-calibrate.zh.html";
  return new URL("./learn/" + file, import.meta.url).href;
}

// The whole way for a newcomer: from a picture they love to a disc they can look at.
export const firstDiscLabel = english => english ? "Burn a disc of a character you love" : "刻一张你喜欢的角色盘";

export function firstDiscURL(english) {
  const file = english ? "first-colour-disc.html" : "first-colour-disc.zh.html";
  return new URL("./learn/" + file, import.meta.url).href;
}
