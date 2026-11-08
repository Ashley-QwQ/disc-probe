// Pure CPU work stays off the UI thread. No network or filesystem access here.
import { processRGBA, applyChromaKey, renderOutput, physicalPreview } from './processing.mjs';

self.onmessage = ({ data: message }) => {
  const { id, operation, image, adjustments, options, key, previewScale } = message;
  try {
    let result;
    if (operation === 'layer') {
      const source = key ? applyChromaKey(image, key) : image;
      result = processRGBA(source, adjustments, { previewScale });
    } else if (operation === 'output') {
      result = renderOutput(image, options);
    } else if (operation === 'soft') {
      result = physicalPreview(image, options);
    } else {
      throw new Error('Unknown image operation');
    }
    const transfer = [result.data.buffer];
    if (result.histogram?.buffer) transfer.push(result.histogram.buffer);
    self.postMessage({ id, result }, transfer);
  } catch (error) {
    self.postMessage({ id, error: String(error.message || error) });
  }
};
