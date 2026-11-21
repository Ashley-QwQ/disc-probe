export const learnLabel = english => english ? "How a disc becomes a picture" : "光盘怎么变成图";

export function learnURL(english) {
  const file = english ? "how-disc-images-work.html" : "how-disc-images-work.zh.html";
  return new URL("./learn/" + file, import.meta.url).href;
}
