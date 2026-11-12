/** Incremental SSE parser for the assistant stream (axios hands us the text so far). */

export function takeFrames(buffer) {
  const frames = [];
  let rest = buffer;
  while (rest.includes('\n\n')) {
    const end = rest.indexOf('\n\n');
    const raw = rest.slice(0, end);
    rest = rest.slice(end + 2);
    const eventLine = raw.split('\n').find((line) => line.startsWith('event: '));
    const dataLine = raw.split('\n').find((line) => line.startsWith('data: '));
    const event = eventLine ? eventLine.slice(7).trim() : 'message';
    const data = dataLine ? JSON.parse(dataLine.slice(6)) : {};
    frames.push({ event, data });
  }
  return { frames, rest };
}
